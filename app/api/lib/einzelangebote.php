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
            if (!is_numeric($qty) || (float)$qty <= 0 || (float)$qty > 99999) throw new InvalidArgumentException("Ungültige Menge bei „{$name}“ (0,01 bis 99.999 kg).");
            $qty = round((float)$qty, 2);
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
                       'offerId' => 'e-' . $e['id'], 'offerName' => $titel, 'einzel' => true, 'nr' => $e['nr'], 'gueltigBis' => $e['gueltigBis'] ?? null],
            'sections' => [], 'groups' => [['id' => $gid, 'name' => $titel, 'section' => '']], 'items' => $items,
            'publishedAt' => (string)($e['freigegebenAt'] ?? $e['changed'] ?? '')];
}

/* ---------- Artikelsuche im Eingabebereich ---------- */
/* Alle bekannten Artikel: Stammdaten, Bestand (eingelagert, erfasst, gesamt) und Preis im Wochenangebot */
function einzel_artikel(bool $mitBestand): array
{
    $by = [];
    $put = function (string $code, string $name) use (&$by) {
        $k = code_key($code);
        if (!isset($by[$k])) $by[$k] = ['code' => $code, 'name' => $name, 'category' => null, 'condition' => null, 'stdPrice' => null, 'inOffer' => false];
        elseif ($by[$k]['name'] === '' && $name !== '') $by[$k]['name'] = $name;
        return $k;
    };
    foreach ((store_read('stammdaten')['articles'] ?? []) as $a) {
        if (($a['code'] ?? '') === '') continue;
        $k = $put((string)$a['code'], (string)($a['name'] ?? ''));
        $by[$k]['category'] = $a['category'] ?? null; $by[$k]['condition'] = $a['condition'] ?? null;
    }
    $pub = store_read('angebot');
    if ($pub) {
        foreach (offer_resolve($pub, offer_def(OFFER_STD))['items'] as $it) {
            if (($it['code'] ?? '') === '') continue;
            $k = $put((string)$it['code'], (string)$it['name']);
            $by[$k]['name'] = (string)$it['name'];   // Bezeichnung wie im Angebot
            $by[$k]['inOffer'] = true;
            if ($by[$k]['stdPrice'] === null) $by[$k]['stdPrice'] = $it['price'];
            $by[$k]['category'] = $by[$k]['category'] ?? ($it['category'] ?? null);
            $by[$k]['condition'] = $by[$k]['condition'] ?? ($it['condition'] ?? null);
        }
    }
    $st = store_read('bestand');
    if ($mitBestand && $st) {
        $inc = [];
        foreach ($st['incoming'] ?? [] as $z) $inc[code_key((string)$z['code'])] = ($inc[code_key((string)$z['code'])] ?? 0) + (float)$z['kg'];
        foreach ($st['articles'] ?? [] as $a) {
            $k = $put((string)$a['code'], (string)$a['name']);
            $by[$k]['kg'] = (float)$a['kg']; $by[$k]['mhd'] = $a['mhd'] ?? null;
        }
        foreach ($inc as $k => $kg) if (!isset($by[$k])) {
            foreach ($st['incoming'] as $z) if (code_key((string)$z['code']) === $k) { $put((string)$z['code'], (string)$z['name']); break; }
        }
        foreach ($by as $k => $a) {
            $by[$k]['kg'] = round($a['kg'] ?? 0.0, 3);
            $by[$k]['incomingKg'] = round($inc[$k] ?? 0.0, 3);
            $by[$k]['totalKg'] = round($by[$k]['kg'] + $by[$k]['incomingKg'], 3);
            $by[$k]['mhd'] = $a['mhd'] ?? null;
        }
    }
    $out = array_values($by);
    usort($out, function ($a, $b) { return strnatcasecmp($a['code'], $b['code']); });
    return ['articles' => $out, 'bestand' => $mitBestand && $st ? ['date' => $st['date'] ?? null] : null, 'angebot' => $pub ? ['publishedAt' => $pub['publishedAt'] ?? null, 'week' => $pub['meta']['week'] ?? null, 'year' => $pub['meta']['year'] ?? null] : null];
}

/* ---------- E-Mail an den Kunden ---------- */
function mail_tpl_einzel(array $c, array $e, string $note): array
{
    global $CFG;
    $titel = einzel_titel($e);
    $subject = "Ihr Angebot {$e['nr']} – {$CFG['company']}";
    $bis = !empty($e['gueltigBis']) ? date('d.m.Y', strtotime($e['gueltigBis'])) : '';
    $intro = 'gerne bieten wir Ihnen an' . ($bis !== '' ? " (gültig bis $bis)" : '') . ':';
    $sig = mail_settings()['signature'];
    $login = !empty($c['login']['active']) ? ($c['login']['username'] ?? '') : '';
    $url = mail_base_url() . '/?angebot=e-' . $e['id'];
    $pr = function ($p) { return $p['price'] !== null ? de_num((float)$p['price']) . ' €/kg' : 'Preis auf Anfrage'; };
    $su = einzel_summe($e);
    $t = mail_greeting($c) . "\n\n" . $intro . "\n\n" . ($note !== '' ? $note . "\n\n" : '') . "$titel ({$e['nr']})\n";
    foreach ($e['positions'] as $p) $t .= '- ' . ($p['code'] !== '' ? $p['code'] . ' ' : '') . $p['name'] . ($p['notiz'] !== '' ? ' (' . $p['notiz'] . ')' : '') . ': ' . $pr($p) . ($p['qty'] !== null ? ', ' . de_qty($p['qty']) . ' kg' : '') . "\n";
    if ($su['summe'] > 0) $t .= "\nWarenwert (ca.): " . de_num($su['summe']) . " €\n";
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
        . '<p style="margin:0 0 8px;font-weight:600;">' . mail_h($titel) . ' <span style="color:#857c72;font-weight:400;">(' . mail_h($e['nr']) . ')</span></p>'
        . '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;border-collapse:collapse;margin:0 0 12px;"><tr><th ' . $th . '>Art.-Nr.</th><th ' . $th . '>Artikel</th><th ' . $thr . '>Menge</th><th ' . $thr . '>Preis</th></tr>';
    foreach ($e['positions'] as $p) {
        $h .= '<tr><td ' . $td . '>' . mail_h($p['code']) . '</td><td ' . $td . '>' . mail_h($p['name']) . ($p['notiz'] !== '' ? '<br><span style="font-size:12px;color:#857c72;">' . mail_h($p['notiz']) . '</span>' : '') . '</td><td ' . $tdr . '>'
            . ($p['qty'] !== null ? mail_h(de_qty($p['qty'])) . ' kg' : '') . '</td><td ' . $tdr . '><strong>' . mail_h($pr($p)) . '</strong></td></tr>';
    }
    $h .= '</table>' . ($su['summe'] > 0 ? '<p style="margin:0 0 12px;text-align:right;">Warenwert (ca.): <strong>' . mail_h(de_num($su['summe'])) . ' €</strong></p>' : '')
        . ($e['hinweis'] !== '' ? '<p style="margin:0 0 14px;">' . nl2br(mail_h($e['hinweis'])) . '</p>' : '')
        . '<p style="margin:0 0 14px;font-size:12.5px;color:#857c72;">Preise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.</p>';
    if ($login !== '' && einzel_sichtbar($e)) $h .= mail_button($url, 'Angebot im Portal ansehen') . '<p style="margin:8px 0 0;font-size:13px;color:#4a443e;">Anmeldung mit Ihrer Benutzerkennung <strong>' . mail_h($login) . '</strong>.</p>';
    return [$subject, $t, mail_layout($subject, $h, $sig, mail_footer('zugang'))];
}
