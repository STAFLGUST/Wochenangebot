<?php
declare(strict_types=1);
/* Einzelangebote: ein Angebot für genau einen Kunden (Angebot bearbeiten → Einzelangebote).
   Dokument „einzelangebote“: { seq: {Jahr: Nummer}, list: [Einzelangebot] }.
   Einzelangebot: { id, nr (E-JJJJ-0001), kid, titel, gueltigBis, hinweis, positions: [{ code, name, qty, price, notiz }],
                    status (entwurf|freigegeben|zurueckgezogen), revision, created(By), changed(By), freigegebenAt, gesendet: [...] }
   Freigegebene, gültige Einzelangebote sieht der Kunde im Portal als eigenes Angebot (Kennung „e-<id>“) und kann daraus
   bestellen; Preise rechnet der Server aus dem Einzelangebot (Regel 10). Bestand erscheint nie beim Kunden (Regel 7). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const EINZEL_STATUS = ['entwurf', 'freigegeben', 'zurueckgezogen'];
const EINZEL_MAX_POS = 300;

function einzel_load(): array
{
    $d = store_read('einzelangebote');
    return ['seq' => is_array($d['seq'] ?? null) ? $d['seq'] : [], 'list' => is_array($d['list'] ?? null) ? $d['list'] : []];
}
function einzel_find(array $d, string $id): ?int
{
    foreach ($d['list'] as $i => $e) if (($e['id'] ?? '') === $id) return $i;
    return null;
}
function einzel_titel(array $e): string { return ($e['titel'] ?? '') !== '' ? $e['titel'] : 'Einzelangebot ' . $e['nr']; }
function einzel_gueltig(array $e): bool { return empty($e['gueltigBis']) || $e['gueltigBis'] >= date('Y-m-d'); }
function einzel_sichtbar(array $e): bool { return ($e['status'] ?? '') === 'freigegeben' && einzel_gueltig($e); }
/* Stand der Freigabe (Millisekunden, immer später als der vorige): Bestellwünsche auf einen älteren Stand werden abgewiesen */
function einzel_stand(?string $prev): string
{
    $t = (int)floor(microtime(true) * 1000);
    if ($prev && ($p = DateTimeImmutable::createFromFormat('Y-m-d\TH:i:s.v\Z', $prev, new DateTimeZone('UTC')))) $t = max($t, (int)$p->format('Uv') + 1);
    return gmdate('Y-m-d\TH:i:s', intdiv($t, 1000)) . sprintf('.%03dZ', $t % 1000);
}

/* Eingaben prüfen (Kopf und Positionen) */
function einzel_clean(array $b): array
{
    $kid = is_string($b['kid'] ?? null) ? $b['kid'] : '';
    $c = null;
    foreach (customers_load()['customers'] as $x) if ($x['id'] === $kid) $c = $x;
    if (!$c) throw new InvalidArgumentException('Bitte einen Kunden wählen.');
    $bis = (string)($b['gueltigBis'] ?? '');
    if ($bis !== '') {
        $d = DateTimeImmutable::createFromFormat('!Y-m-d', $bis);
        if (!$d || $d->format('Y-m-d') !== $bis) throw new InvalidArgumentException('Bitte ein gültiges Datum für „gültig bis“ angeben.');
    }
    $pos = [];
    $in = is_array($b['positions'] ?? null) ? $b['positions'] : [];
    if (count($in) > EINZEL_MAX_POS) throw new InvalidArgumentException('Zu viele Positionen (höchstens ' . EINZEL_MAX_POS . ').');
    foreach ($in as $p) {
        if (!is_array($p)) continue;
        $code = s($p['code'] ?? '', 20) ?? '';
        if ($code !== '' && !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException('Ungültige Artikelnummer in den Positionen.');
        $name = s($p['name'] ?? null, 200, false);
        if ($name === null || $name === '') throw new InvalidArgumentException('Jede Position braucht eine Bezeichnung.');
        $price = $p['price'] ?? null;
        if ($price !== null && $price !== '') {
            if (!is_numeric($price) || (float)$price < 0 || (float)$price >= 100000) throw new InvalidArgumentException("Ungültiger Preis bei „{$name}“.");
            $price = round((float)$price, 2);
        } else $price = null;   // Preis auf Anfrage
        $qty = $p['qty'] ?? null;
        if ($qty !== null && $qty !== '') {
            if (!is_numeric($qty)) throw new InvalidArgumentException("Ungültige Menge bei „{$name}“ (0,01 bis 99.999 kg).");
            $qty = round((float)$qty, 2);   // erst runden, dann prüfen – sonst würde 0,004 als „0 kg“ gespeichert
            if ($qty <= 0 || $qty > 99999) throw new InvalidArgumentException("Ungültige Menge bei „{$name}“ (0,01 bis 99.999 kg).");
        } else $qty = null;
        $pos[] = ['code' => $code, 'name' => $name, 'qty' => $qty, 'price' => $price, 'notiz' => s($p['notiz'] ?? '', 200) ?? ''];
    }
    return [$c, ['kid' => $kid, 'titel' => s($b['titel'] ?? '', 120) ?? '', 'gueltigBis' => $bis !== '' ? $bis : null,
                 'hinweis' => mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', (string)($b['hinweis'] ?? '')) ?? '')), 0, 1000),
                 'positions' => $pos]];
}
/* Summen (Positionen mit Menge und Preis) */
function einzel_summe(array $e): array
{
    $kg = 0.0; $sum = 0.0;
    foreach ($e['positions'] ?? [] as $p) if ($p['qty'] !== null) { $kg += $p['qty']; if ($p['price'] !== null) $sum += round(round($p['price'] * 100) * $p['qty']) / 100; }
    return ['kg' => round($kg, 2), 'summe' => round($sum, 2)];
}
/* Ansicht für den Eingabebereich (mit Kundenname) */
function einzel_view(array $e, array $kunden): array
{
    $c = $kunden[$e['kid']] ?? null;
    return $e + ['firma' => $c['firma'] ?? '(Kunde gelöscht)', 'kundeNr' => $c['nr'] ?? '', 'email' => $c['email'] ?? '', 'hatZugang' => !empty($c['login']['active']),
                 'sichtbar' => einzel_sichtbar($e), 'summen' => einzel_summe($e)];
}
function einzel_kunden_map(): array
{
    $m = [];
    foreach (customers_load()['customers'] as $c) $m[$c['id']] = $c;
    return $m;
}

/* ---------- Portal ---------- */
/* Für den Kunden sichtbare Einzelangebote (freigegeben, noch gültig) */
function einzel_fuer_kunde(array $c): array
{
    return array_values(array_filter(einzel_load()['list'], function ($e) use ($c) { return ($e['kid'] ?? '') === $c['id'] && einzel_sichtbar($e); }));
}
function einzel_von_kennung(string $oid): ?array
{
    if (!preg_match('/^e-([a-f0-9]{10})$/', $oid, $m)) return null;
    $d = einzel_load();
    $i = einzel_find($d, $m[1]);
    return $i === null ? null : $d['list'][$i];
}
/* Angebotsmodell wie offer_resolve() – nur Name, Merkmale und Preis, kein Bestand */
function einzel_model(array $e): array
{
    $master = [];
    foreach ((store_read('stammdaten')['articles'] ?? []) as $a) $master[code_key((string)$a['code'])] = $a;
    $pub = store_read('angebot');   // Merkmale (Fleischart, Herkunft, Zustand) ergänzend aus dem Wochenangebot, nie dessen Preise
    if ($pub) foreach ($pub['items'] ?? [] as $it) {
        $k = code_key((string)($it['code'] ?? ''));
        if ($k === '' || isset($master[$k])) continue;
        $master[$k] = ['category' => $it['category'] ?? null, 'origin' => $it['origin'] ?? null, 'condition' => $it['condition'] ?? null];
    }
    $gid = 'e1';
    $items = [];
    foreach ($e['positions'] as $i => $p) {
        $m = $p['code'] !== '' ? ($master[code_key($p['code'])] ?? null) : null;
        $items[] = ['id' => 'p' . ($i + 1), 'code' => $p['code'], 'name' => $p['name'] . ($p['notiz'] !== '' ? ' – ' . $p['notiz'] : ''),
                    'category' => in_array($m['category'] ?? '', CATEGORIES, true) ? $m['category'] : 'Sonstiges', 'origin' => $m['origin'] ?? null,
                    'condition' => in_array($m['condition'] ?? '', CONDITIONS, true) ? $m['condition'] : 'unbekannt', 'groupId' => $gid,
                    'price' => $p['price'] !== null ? ['status' => 'value', 'value' => $p['price']] : ['status' => 'request'], 'altPrices' => []];
    }
    $titel = einzel_titel($e);
    return ['meta' => ['title' => $titel . (!empty($e['gueltigBis']) ? ' – gültig bis ' . date('d.m.Y', strtotime($e['gueltigBis'])) : ''), 'notice' => 'Einzelangebot',
                       'offerId' => 'e-' . $e['id'], 'offerName' => $titel, 'einzel' => true, 'nr' => $e['nr'], 'gueltigBis' => $e['gueltigBis'] ?? null,
                       'kunde' => einzel_kunden_map()[$e['kid']]['firma'] ?? '', 'hinweis' => (string)($e['hinweis'] ?? '')],   // Hinweis an den Kunden (Bildschirm und Druck)
            'sections' => [], 'groups' => [['id' => $gid, 'name' => $titel, 'section' => '']], 'items' => $items,
            'publishedAt' => (string)($e['freigegebenAt'] ?? $e['changed'] ?? '')];
}

/* ---------- Artikelsuche im Eingabebereich ---------- */
/* Alle bekannten Artikel: Stammdaten (mit Merkmalen und VK-Gruppe), Bestand (eingelagert, erfasst, gesamt; je Partie und
   je erwarteter Lieferung) und Preis im Wochenangebot. Einkaufspreise je Partie nur mit $mitEk („bestand.einkaufspreise“).
   VK-Gruppen: Nummer, Bezeichnung (Stammdaten → VK-Gruppen) und Anzahl Artikel – nur Gruppen, die vorkommen. */
function einzel_artikel(bool $mitBestand, bool $mitEk = false): array
{
    $by = [];
    $put = function (string $code, string $name) use (&$by) {
        $k = code_key($code);
        if (!isset($by[$k])) $by[$k] = ['code' => $code, 'name' => $name, 'category' => null, 'origin' => null, 'condition' => null, 'vk' => null, 'stdPrice' => null, 'inOffer' => false];
        elseif ($by[$k]['name'] === '' && $name !== '') $by[$k]['name'] = $name;
        return $k;
    };
    foreach ((store_read('stammdaten')['articles'] ?? []) as $a) {
        if (($a['code'] ?? '') === '') continue;
        $k = $put((string)$a['code'], (string)($a['name'] ?? ''));
        $by[$k]['category'] = $a['category'] ?? null; $by[$k]['condition'] = $a['condition'] ?? null; $by[$k]['origin'] = $a['origin'] ?? null;
        $by[$k]['vk'] = ($a['vkGruppe'] ?? '') !== '' ? (string)$a['vkGruppe'] : null;
    }
    $pub = store_read('angebot');
    if ($pub) {
        foreach (offer_resolve($pub, offer_def(OFFER_STD))['items'] as $it) {
            if (($it['code'] ?? '') === '') continue;
            $k = $put((string)$it['code'], (string)$it['name']);
            $by[$k]['name'] = (string)$it['name'];   // Bezeichnung wie im Angebot
            $by[$k]['inOffer'] = true;
            if ($by[$k]['stdPrice'] === null) $by[$k]['stdPrice'] = $it['price'];
            foreach (['category', 'origin', 'condition'] as $f) $by[$k][$f] = $by[$k][$f] ?? ($it[$f] ?? null);
        }
    }
    $st = store_read('bestand');
    if ($mitBestand && $st) {
        $inc = [];
        foreach ($st['incoming'] ?? [] as $z) {
            $k = $put((string)$z['code'], (string)($z['name'] ?? ''));
            $inc[$k][] = ['lot' => (string)($z['lot'] ?? ''), 'arrival' => $z['arrival'] ?? null, 'kg' => round((float)$z['kg'], 3)];
        }
        $lots = [];
        foreach ($st['articles'] ?? [] as $a) {
            $k = $put((string)$a['code'], (string)$a['name']);
            $by[$k]['kg'] = (float)$a['kg']; $by[$k]['mhd'] = $a['mhd'] ?? null;
            foreach ($a['lots'] ?? [] as $l) {
                $e = ['lot' => (string)($l['lot'] ?? ''), 'arrival' => $l['arrival'] ?? null, 'mhd' => $l['mhd'] ?? null, 'kolli' => $l['kolli'] ?? null, 'kg' => round((float)($l['kg'] ?? 0), 3)];
                if ($mitEk) $e['ek'] = $l['ek'] ?? null;
                $lots[$k][] = $e;
            }
        }
        foreach ($by as $k => $a) {
            $by[$k]['kg'] = round($a['kg'] ?? 0.0, 3);
            $by[$k]['incomingKg'] = round(array_sum(array_column($inc[$k] ?? [], 'kg')), 3);
            $by[$k]['totalKg'] = round($by[$k]['kg'] + $by[$k]['incomingKg'], 3);
            $by[$k]['mhd'] = $a['mhd'] ?? null;
            $by[$k]['lots'] = $lots[$k] ?? [];
            $by[$k]['incoming'] = $inc[$k] ?? [];
        }
    }
    $out = array_values($by);
    usort($out, function ($a, $b) { return strnatcasecmp($a['code'], $b['code']); });
    $namen = [];
    foreach (gruppen_load('vkgruppen')['groups'] as $g) $namen[code_key($g['nr'])] = $g['name'];
    $vk = [];
    foreach ($out as $a) if ($a['vk'] !== null) {
        $vk[$a['vk']] = $vk[$a['vk']] ?? ['nr' => $a['vk'], 'name' => $namen[code_key($a['vk'])] ?? null, 'anzahl' => 0];
        $vk[$a['vk']]['anzahl']++;
    }
    $vk = array_values($vk);
    usort($vk, function ($a, $b) { return strnatcasecmp($a['nr'], $b['nr']); });
    return ['articles' => $out, 'vkGruppen' => $vk, 'ek' => $mitBestand && $mitEk,
            'bestand' => $mitBestand && $st ? ['date' => $st['date'] ?? null] : null,
            'angebot' => $pub ? ['publishedAt' => $pub['publishedAt'] ?? null, 'week' => $pub['meta']['week'] ?? null, 'year' => $pub['meta']['year'] ?? null] : null];
}

/* ---------- PDF im Design der Angebotsansicht (A4 quer, drei Spalten) ---------- */
/* Wie die Druckliste der Angebotsseite: Logo und Titel, Blöcke mit Kopfzeile „€ / kg“, Zebrastreifen, Seitenzahlen.
   Nur Positionen, Preise, Mengen und Hinweise – nie Bestand, Partien oder Einkaufspreise (Regel 7). */
function einzel_pdf(array $e, ?array $c): string
{
    global $CFG;
    require_once __DIR__ . '/pdf.php';
    $pdf = new Pdf();
    $W = $pdf->w; $H = $pdf->h;
    $ML = 28.35; $MT = 25.5; $MB = 34; $GAP = 16; $K = 3;
    $colW = ($W - 2 * $ML - ($K - 1) * $GAP) / $K;
    $wCode = 38; $wPrice = 52; $wName = $colW - $wCode - $wPrice - 8;
    $LH = 10.4; $FS = 8.6;
    $titel = einzel_titel($e);
    $bis = !empty($e['gueltigBis']) ? date('d.m.Y', strtotime($e['gueltigBis'])) : '';
    $firma = $c['firma'] ?? '';
    $stand = date('d.m.Y', strtotime((string)($e['freigegebenAt'] ?? $e['changed'] ?? 'now')) ?: time());   // wie die Angebotsseite: Stand des Angebots, nicht Druckdatum
    // Text auf eine Breite kürzen (mit „…“) – lange Titel, Firmen oder Artikelnummern laufen sonst über Spalten und Seitenrand
    $fit = function (string $t, float $size, float $max, bool $bold = false): string {
        if (Pdf::width($t, $size, $bold) <= $max) return $t;
        while ($t !== '' && Pdf::width($t . '…', $size, $bold) > $max) $t = mb_substr($t, 0, -1);
        return rtrim($t) . '…';
    };

    // Bausteine: Kopf eines Blocks, Zeilen, Abschlusstexte
    $rows = [];
    foreach ($e['positions'] as $i => $p) {
        $name = $p['name'] . ($p['notiz'] !== '' ? ' – ' . $p['notiz'] : '');
        $lines = Pdf::wrap($name, $FS, $wName);
        $eigen = Pdf::width($p['code'], $FS) > $wCode - 6;   // lange (freie) Artikelnummer: eigene Zeile über der Bezeichnung statt Überlappung
        $h = 4.6 + (count($lines) + ($eigen ? 1 : 0)) * $LH + ($p['qty'] !== null ? 9 : 0);
        $rows[] = ['t' => 'row', 'p' => $p, 'lines' => $lines, 'h' => $h, 'z' => $i % 2 === 0, 'eigen' => $eigen];
    }
    $tail = [];
    $su = einzel_summe($e);
    if ($su['summe'] > 0) $tail[] = ['Warenwert (ca.): ' . de_num($su['summe']) . ' € bei ' . de_qty($su['kg']) . ' kg', true];
    if (($e['hinweis'] ?? '') !== '') foreach (explode("\n", $e['hinweis']) as $l) $tail[] = [$l, false];
    $tail[] = ['Preise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.', false];
    foreach (fracht_hinweis() as $l) $tail[] = [$l, false];
    $tailLines = [];
    foreach ($tail as [$t, $b]) foreach (Pdf::wrap($t, 8, $colW, $b) as $l) $tailLines[] = [$l, $b];
    $tailH = 10 + count($tailLines) * 10.5;

    // Spalten füllen: Seite 1 mit Kopf, kurze Angebote nicht künstlich auf drei Spalten verteilen
    $headH = 58;
    $top = fn(int $page) => $MT + ($page === 0 ? $headH : 0);
    $bottom = $H - $MB;
    $total = array_sum(array_column($rows, 'h'));
    $ziel = max(170, $total / $K + 30);
    $pages = [[[]]]; $pg = 0; $col = 0; $y = $top(0) + 18;
    $neueSpalte = function () use (&$pages, &$pg, &$col, &$y, $K, $top) {
        $col++;
        if ($col >= $K) { $pages[] = [[]]; $pg++; $col = 0; } else $pages[$pg][$col] = [];
        $y = $top($pg) + 18;   // Platz für den Blockkopf
    };
    foreach ($rows as $r) {
        if ($pages[$pg][$col] && $y + $r['h'] > ($pg === 0 && count($pages) === 1 ? min($bottom, $top(0) + 18 + $ziel) : $bottom)) $neueSpalte();
        $pages[$pg][$col][] = $r + ['y' => $y];
        $y += $r['h'];
    }
    if ($y + $tailH > $bottom) $neueSpalte();
    $pages[$pg][$col][] = ['t' => 'tail', 'y' => $y + 8];

    $n = count($pages);
    foreach ($pages as $pi => $cols) {
        if ($pi > 0) $pdf->addPage();
        if ($pi === 0) {
            $lh = $pdf->jpeg(__DIR__ . '/druck-logo.jpg', $ML, $MT, 135);
            $tx = $ML + 135 + 16;
            $pdf->text($tx, $MT + 19, $fit($titel, 15, $W - $ML - $tx, true), 15, true);
            $sub = 'Angebot ' . $e['nr'] . ($firma !== '' ? ' für ' . $firma : '') . ($bis !== '' ? ' · gültig bis ' . $bis : '') . ' · Stand ' . $stand . ' · Preise in € je kg';
            $pdf->text($tx, $MT + 34, $fit($sub, 8.6, $W - $ML - $tx), 8.6, false, '#555555');
            $pdf->line($ML, $MT + max($lh, 40) + 8, $W - $ML, $MT + max($lh, 40) + 8, 1.4, '#8c1d2c');
        }
        foreach ($cols as $ci => $items) {
            if (!$items) continue;
            $x = $ML + $ci * ($colW + $GAP);
            $hasRows = (bool)array_filter($items, fn($i) => $i['t'] === 'row');
            if ($hasRows) {
                $hy = $top($pi) + 11;
                $cont = $pi > 0 || $ci > 0;
                $pdf->text($x + 3, $hy, $fit($titel, 9.2, $colW - 60 - ($cont ? Pdf::width(' (Forts.)', 9.2, true) : 0), true) . ($cont ? ' (Forts.)' : ''), 9.2, true);
                $pdf->text($x + $colW - 4, $hy, '€ / kg', 8, true, '#111111', 'r');
                $pdf->line($x, $hy + 4.5, $x + $colW, $hy + 4.5, 1.1);
            }
            foreach ($items as $it) {
                if ($it['t'] === 'tail') {
                    $ty = $it['y'];
                    foreach ($tailLines as [$l, $b]) { $ty += 10.5; $pdf->text($x + 3, $ty, $l, 8, $b, $b ? '#111111' : '#444444'); }
                    continue;
                }
                $p = $it['p']; $ry = $it['y'];
                if ($it['z']) $pdf->rect($x, $ry, $colW, $it['h'], '#f1f1ee');
                $by = $ry + 3 + $LH - 2.2;
                $pdf->text($x + 3, $by, $it['eigen'] ? $fit($p['code'], $FS, $colW - $wPrice - 8) : $p['code'], $FS);
                if ($it['eigen']) $by += $LH;
                foreach ($it['lines'] as $li => $l) $pdf->text($x + $wCode, $by + $li * $LH, $l, $FS);
                if ($p['qty'] !== null) $pdf->text($x + $wCode, $by + count($it['lines']) * $LH - 1, 'Menge ' . de_qty($p['qty']) . ' kg', 7.4, false, '#555555');
                if ($p['price'] !== null) $pdf->text($x + $colW - 4, $by, de_num((float)$p['price']), $FS + .2, true, '#111111', 'r');
                else $pdf->text($x + $colW - 4, $by, 'auf Anfrage', 7.4, false, '#666666', 'r');
            }
        }
        $fy = $H - 16;
        $pdf->text($ML, $fy, $fit(($CFG['company'] ?? '') . ' · Angebot ' . $e['nr'] . ' · ' . $titel . ' · Preise in € je kg', 7, $W - 2 * $ML - 70), 7, false, '#777777');
        $pdf->text($W - $ML, $fy, 'Seite ' . ($pi + 1) . ' von ' . $n, 7, false, '#777777', 'r');
    }
    return $pdf->output('Angebot ' . $e['nr'] . ' – ' . $titel);
}
function plural_de(int $n, string $eins, string $viele): string { return $n . ' ' . ($n === 1 ? $eins : $viele); }
function einzel_pdf_name(array $e): string { return 'Angebot_' . preg_replace('/[^A-Za-z0-9-]/', '', $e['nr']) . '.pdf'; }

/* ---------- E-Mail an den Kunden ---------- */
/* $format: „liste“ = Positionen als Tabelle in der E-Mail (bisher), „pdf“ = kurze Nachricht, Angebot als PDF im Anhang */
function mail_tpl_einzel(array $c, array $e, string $note, string $format = 'liste'): array
{
    $pdf = $format === 'pdf';
    global $CFG;
    $titel = einzel_titel($e);
    $subject = "Ihr Angebot {$e['nr']} – {$CFG['company']}";
    $bis = !empty($e['gueltigBis']) ? date('d.m.Y', strtotime($e['gueltigBis'])) : '';
    $intro = $pdf ? 'anbei erhalten Sie unser Angebot ' . $e['nr'] . ' als PDF' . ($bis !== '' ? " (gültig bis $bis)" : '') . '.'
                  : 'gerne bieten wir Ihnen an' . ($bis !== '' ? " (gültig bis $bis)" : '') . ':';
    $sig = mail_settings()['signature'];
    $login = !empty($c['login']['active']) ? ($c['login']['username'] ?? '') : '';
    $url = mail_base_url() . '/?angebot=e-' . $e['id'];
    $pr = function ($p) { return $p['price'] !== null ? de_num((float)$p['price']) . ' €/kg' : 'Preis auf Anfrage'; };
    $su = einzel_summe($e);
    $t = mail_greeting($c) . "\n\n" . $intro . "\n\n" . ($note !== '' ? $note . "\n\n" : '') . "$titel ({$e['nr']})\n";
    if ($pdf) $t .= 'Anhang: ' . einzel_pdf_name($e) . ' (' . plural_de(count($e['positions']), 'Position', 'Positionen') . ")\n";
    else foreach ($e['positions'] as $p) $t .= '- ' . ($p['code'] !== '' ? $p['code'] . ' ' : '') . $p['name'] . ($p['notiz'] !== '' ? ' (' . $p['notiz'] . ')' : '') . ': ' . $pr($p) . ($p['qty'] !== null ? ', ' . de_qty($p['qty']) . ' kg' : '') . "\n";
    if ($su['summe'] > 0 && !$pdf) $t .= "\nWarenwert (ca.): " . de_num($su['summe']) . " €\n";
    if ($e['hinweis'] !== '') $t .= "\n" . $e['hinweis'] . "\n";
    $t .= "\nPreise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.\n";
    if ($login !== '' && einzel_sichtbar($e)) $t .= "\nIm Angebotsportal (Anmeldung mit Ihrer Benutzerkennung $login):\n$url\n";
    $t .= "\n" . $sig . "\n\n-- \n" . mail_footer('zugang') . "\n";
    $td = 'style="padding:7px 6px;border-bottom:1px solid #eee8e1;vertical-align:top;"';
    $tdr = 'style="padding:7px 6px;border-bottom:1px solid #eee8e1;text-align:right;white-space:nowrap;vertical-align:top;"';
    $th = 'style="text-align:left;padding:6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $thr = 'style="text-align:right;padding:6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $h = '<p style="margin:0 0 14px;">' . mail_h(mail_greeting($c)) . '</p><p style="margin:0 0 14px;">' . mail_h($intro) . '</p>'
        . ($note !== '' ? '<p style="margin:0 0 14px;padding:12px 14px;background:#f7efe9;border-radius:8px;">' . nl2br(mail_h($note)) . '</p>' : '')
        . '<p style="margin:0 0 8px;font-weight:600;">' . mail_h($titel) . ' <span style="color:#857c72;font-weight:400;">(' . mail_h($e['nr']) . ')</span></p>';
    if ($pdf) $h .= '<p style="margin:0 0 14px;padding:10px 14px;border:1px solid #e6e0d8;border-radius:8px;">Anhang: <strong>' . mail_h(einzel_pdf_name($e)) . '</strong>' . ' <span style="color:#857c72;">· '
        . mail_h(plural_de(count($e['positions']), 'Position', 'Positionen')) . '</span></p>';
    else {
    $h .= '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;border-collapse:collapse;margin:0 0 12px;"><tr><th ' . $th . '>Art.-Nr.</th><th ' . $th . '>Artikel</th><th ' . $thr . '>Menge</th><th ' . $thr . '>Preis</th></tr>';
    foreach ($e['positions'] as $p) {
        $h .= '<tr><td ' . $td . '>' . mail_h($p['code']) . '</td><td ' . $td . '>' . mail_h($p['name']) . ($p['notiz'] !== '' ? '<br><span style="font-size:12px;color:#857c72;">' . mail_h($p['notiz']) . '</span>' : '') . '</td><td ' . $tdr . '>'
            . ($p['qty'] !== null ? mail_h(de_qty($p['qty'])) . ' kg' : '') . '</td><td ' . $tdr . '><strong>' . mail_h($pr($p)) . '</strong></td></tr>';
    }
    $h .= '</table>' . ($su['summe'] > 0 ? '<p style="margin:0 0 12px;text-align:right;">Warenwert (ca.): <strong>' . mail_h(de_num($su['summe'])) . ' €</strong></p>' : '');
    }
    $h .= ($e['hinweis'] !== '' ? '<p style="margin:0 0 14px;">' . nl2br(mail_h($e['hinweis'])) . '</p>' : '')
        . '<p style="margin:0 0 14px;font-size:12.5px;color:#857c72;">Preise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.</p>';
    if ($login !== '' && einzel_sichtbar($e)) $h .= mail_button($url, 'Angebot im Portal ansehen') . '<p style="margin:8px 0 0;font-size:13px;color:#4a443e;">Anmeldung mit Ihrer Benutzerkennung <strong>' . mail_h($login) . '</strong>.</p>';
    return [$subject, $t, mail_layout($subject, $h, $sig, mail_footer('zugang'))];
}
