<?php
declare(strict_types=1);
/* CRM · Mein Cockpit, Master-Cockpit und die Übersicht im Kunden-Pop-up (Auftrag des Inhabers 01.11.2026).
   „Mein Cockpit“: die Kunden des Vertreters, der dem Mitarbeiter in der Verwaltung zugeordnet ist (Feld „vertreter“ am Nutzer)
   – Kunden, bei denen er Vertreter oder Vertreter 2 ist. Master-Cockpit (Recht crm.master; Administratoren haben alle Rechte):
   alle Vertreter im Vergleich und der Umschalter auf die Ansicht jedes Vertreters bzw. der Kunden ohne Vertreter.
   Zahlen und Signale rechnet das Controlling (module/controlling/kundenbild.php, nur über dessen Funktionen –
   regeln/datenverantwortung.toml); das CRM ordnet sie den Vertretern zu, summiert und gibt nur aus, was der Mitarbeiter sehen
   darf: Umsätze in € nur mit crm.umsatz_euro, Mengen nur mit crm.umsatz_kg (GR-103, serverseitig). Nie EK-Werte, DB oder Spanne.
   Signale ohne Beträge (Bestellpause, „kauft weniger −28 %“, Artikel nicht mehr gekauft, neu) sieht jeder mit „CRM ansehen“. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const CRM_COCKPIT_SIGNALE = 60;   // je Art höchstens so viele Signale
const CRM_COCKPIT_TOP = 10;       // Top-Kunden
const CRM_COCKPIT_ARTEN = ['pause', 'weniger', 'weg', 'neu'];

/* Schnittstelle des Controllings laden (nur, wenn das CRM Zahlen braucht) */
function crm_kundenbild(): void { require_once __DIR__ . '/../controlling/kundenbild.php'; }

/* Welche Zahlen darf der Mitarbeiter sehen? */
function crm_zahlrechte(array $me): array { return ['euro' => may($me, 'crm.umsatz_euro'), 'kg' => may($me, 'crm.umsatz_kg'), 'master' => may($me, 'crm.master')]; }

/* [Umsatz, Menge] → nur die erlaubten Werte: umsatz (Cent), menge (Tausendstel kg) */
function crm_um(array $w, array $r): array|object
{
    $o = [];
    if ($r['euro']) $o['umsatz'] = (int)$w[0];
    if ($r['kg']) $o['menge'] = (int)$w[1];
    return $o ?: (object)[];   // ohne beide Rechte: {} (als Objekt, wie mit Werten)
}

/* Felder umsatz…/menge… (auch in Listen darin) ohne das jeweilige Recht entfernen */
function crm_zahlen_filtern(array $x, array $r): array
{
    foreach ($x as $k => $v) {
        if (is_array($v)) { $x[$k] = crm_zahlen_filtern($v, $r); continue; }
        if (!is_string($k)) continue;
        if ((!$r['euro'] && str_starts_with($k, 'umsatz')) || (!$r['kg'] && str_starts_with($k, 'menge'))) unset($x[$k]);
    }
    return $x;
}

/* Ansicht: 'vertreter' (Nummer), 'master' (alle), 'ohne_vertreter' (Master: Kunden ohne Vertreter) oder 'ohne' (kein Vertreter
   zugeordnet, kein Master-Recht: nur Wiedervorlagen, Chancen, Aktivitäten). Ohne Wunsch: der eigene Vertreter, sonst Master.
   Andere Vertreter und „alle“ nur mit crm.master. */
function crm_cockpit_ansicht(array $me, ?string $wunsch): array
{
    $master = may($me, 'crm.master');
    $ich = (string)($me['vertreter'] ?? '');
    if ($wunsch === null || $wunsch === '') $wunsch = $ich !== '' ? $ich : ($master ? 'alle' : 'ohne');
    if (!$master) {
        if ($wunsch === 'ohne' && $ich === '') return ['art' => 'ohne', 'vertreter' => null];
        if ($wunsch !== $ich) fail('Die Ansicht anderer Vertreter und das Master-Cockpit sehen nur Mitarbeiter mit dem Recht „CRM: Master-Cockpit“.', 403);
        return ['art' => 'vertreter', 'vertreter' => $ich];
    }
    if ($wunsch === 'alle' || $wunsch === 'ohne') return ['art' => 'master', 'vertreter' => null];
    if ($wunsch === '_') return ['art' => 'ohne_vertreter', 'vertreter' => '_'];
    if ($wunsch !== $ich && !in_array($wunsch, array_column(crm_vertreter(), 'nr'), true)) fail('Diesen Vertreter gibt es nicht.', 404);
    return ['art' => 'vertreter', 'vertreter' => $wunsch];
}

/* Gehört der Kunde der Verwaltung zur Ansicht? */
function crm_im_bereich(array $c, array $a): bool
{
    $v1 = (string)($c['vertreter'] ?? ''); $v2 = (string)($c['vertreter2'] ?? '');
    if ($a['art'] === 'master') return true;
    if ($a['art'] === 'ohne_vertreter') return $v1 === '' && $v2 === '';
    return $a['art'] === 'vertreter' && ($v1 === $a['vertreter'] || $v2 === $a['vertreter']);
}

/* Reihenfolge der Signale je Art: wirtschaftlich größte zuerst – nach dem, was der Mitarbeiter sehen darf (€, sonst kg) */
function crm_signal_gewicht(array $s, array $r): float
{
    $u = $r['euro']; $m = $r['kg'];
    switch ($s['art']) {
        case 'pause': return $u ? $s['umsatzMonat'] : ($m ? $s['mengeMonat'] : $s['pause']);
        case 'weniger': return $u ? $s['umsatzBasis'] - $s['umsatz'] : ($m ? $s['mengeBasis'] - $s['menge'] : -$s['anteil']);
        case 'weg': return $u ? array_sum(array_column($s['artikel'], 'umsatz')) : ($m ? array_sum(array_column($s['artikel'], 'menge')) : $s['anzahl']);
        case 'neu': return $u ? $s['umsatz'] : ($m ? $s['menge'] : $s['kauftage']);
    }
    return 0;
}

/* Cockpit der Ansicht: Kennzahlen (Monat und Jahr bis zum Stand mit Vorjahr, 365 Tage), Signale, Top-Kunden und – im
   Master-Cockpit – die Vertreter im Vergleich (Kunden mit zwei Vertretern zählen bei beiden). */
function crm_cockpit(array $me, ?string $wunsch): array
{
    $r = crm_zahlrechte($me);
    $a = crm_cockpit_ansicht($me, $wunsch);
    $o = ['ok' => true, 'ansicht' => $a['art'], 'vertreter' => $a['vertreter'], 'ich' => (string)($me['vertreter'] ?? ''), 'rechte' => $r,
          'stand' => null, 'von' => null, 'monat' => null, 'vorjahr' => null, 'monate' => [], 'kennzahlen' => null, 'signale' => [], 'top' => [], 'vergleich' => null];
    if ($a['art'] === 'ohne') return $o;
    $stamm = crm_stammkunden();
    $keyJeNr = []; $aktiv = 0;
    foreach ($stamm as $id => $c) {
        if (!crm_im_bereich($c, $a)) continue;
        if (!empty($c['active'])) $aktiv++;
        $nr = trim((string)($c['nr'] ?? ''));
        if ($nr !== '') $keyJeNr[code_key($nr)] = (string)$id;
    }
    crm_kundenbild();
    $kb = kundenbild_kunden($a['art'] === 'master' ? null : array_keys($keyJeNr));
    $o = array_merge($o, ['stand' => $kb['stand'], 'von' => $kb['von'], 'monat' => $kb['monat'], 'vorjahr' => $kb['vorjahr'], 'monate' => $kb['monate']]);
    $fenster = ['monat', 'vjMonat', 'jahr', 'vjJahr', 'j365', 'v365'];
    $sum = array_fill_keys($fenster, [0, 0]);
    $mitKauf = 0; $ohneStamm = 0; $neu = 0;
    $sig = array_fill_keys(CRM_COCKPIT_ARTEN, []);
    $top = [];
    foreach ($kb['kunden'] as $kk => $z) {
        foreach ($fenster as $w) { $sum[$w][0] += $z['w'][$w][0]; $sum[$w][1] += $z['w'][$w][1]; }
        if ($z['kauftage'] > 0) $mitKauf++;
        $key = $keyJeNr[(string)$kk] ?? null;
        if ($key === null) { $ohneStamm++; continue; }   // Umsatz ohne Kundenstammsatz: nur in den Summen (Master)
        $c = $stamm[$key];
        $kopf = ['key' => $key, 'nr' => (string)$c['nr'], 'firma' => (string)($c['firma'] ?? ''), 'ort' => trim((string)($c['plz'] ?? '') . ' ' . (string)($c['ort'] ?? '')),
                 'vertreter' => (string)($c['vertreter'] ?? ''), 'vertreter2' => (string)($c['vertreter2'] ?? '')];
        foreach ($z['signale'] as $s) { if ($s['art'] === 'neu') $neu++; $sig[$s['art']][] = $kopf + $s + ['_g' => crm_signal_gewicht($s, $r)]; }
        $top[] = $kopf + ['_g' => $r['euro'] ? $z['w']['j365'][0] : $z['w']['j365'][1], 'j365' => crm_um($z['w']['j365'], $r), 'v365' => crm_um($z['w']['v365'], $r),
                 'reihe' => array_map(fn($w) => crm_um($w, $r), $z['reihe']), 'zuletzt' => $z['zuletzt'], 'kauftage' => $z['kauftage']];
    }
    $liste = [];
    foreach ($sig as $art => $l) {
        usort($l, fn($x, $y) => $y['_g'] <=> $x['_g'] ?: strcmp($x['nr'], $y['nr']));
        foreach (array_slice($l, 0, CRM_COCKPIT_SIGNALE) as $s) { unset($s['_g']); $liste[] = crm_zahlen_filtern($s, $r); }
    }
    $o['signale'] = $liste;
    $o['signaleGesamt'] = array_map('count', $sig);
    if ($r['euro'] || $r['kg']) {   // ohne € und kg keine Rangliste der Kunden (die Reihenfolge verriete die Größe)
        usort($top, fn($x, $y) => $y['_g'] <=> $x['_g'] ?: strcmp($x['nr'], $y['nr']));
        $o['top'] = array_map(function ($t) { unset($t['_g']); return $t; }, array_slice(array_values(array_filter($top, fn($t) => $t['_g'] > 0)), 0, CRM_COCKPIT_TOP));
    }
    $o['kennzahlen'] = ['kunden' => $aktiv, 'mitKauf' => $mitKauf, 'neu' => $neu, 'ohneStammsatz' => $a['art'] === 'master' ? $ohneStamm : 0]
        + array_map(fn($w) => crm_um($w, $r), $sum);
    if ($a['art'] === 'master') $o['vergleich'] = crm_cockpit_vergleich($stamm, $kb, $r);
    return $o;
}

/* Master-Cockpit: je Vertreter (und „ohne Vertreter“) aktive Kunden, Umsatz/Menge im Monat mit Vorjahr und in 365 Tagen, Signale */
function crm_cockpit_vergleich(array $stamm, array $kb, array $r): array
{
    $zeilen = [];
    foreach (crm_vertreter() as $v) $zeilen[$v['nr']] = ['nr' => $v['nr'], 'name' => $v['name']];
    $zeilen['_'] = ['nr' => '_', 'name' => 'ohne Vertreter'];
    $sum = [];
    foreach ($zeilen as $nr => $_) $sum[$nr] = ['kunden' => 0, 'monat' => [0, 0], 'vjMonat' => [0, 0], 'j365' => [0, 0], 'v365' => [0, 0], 'signale' => array_fill_keys(CRM_COCKPIT_ARTEN, 0)];
    foreach ($stamm as $c) {
        $v1 = (string)($c['vertreter'] ?? ''); $v2 = (string)($c['vertreter2'] ?? '');
        $bei = array_values(array_unique(array_filter([$v1, $v2], fn($x) => $x !== '')));
        if (!$bei) $bei = ['_'];
        $nr = trim((string)($c['nr'] ?? ''));
        $z = $nr !== '' ? ($kb['kunden'][code_key($nr)] ?? null) : null;
        foreach ($bei as $v) {
            if (!isset($sum[$v])) { $zeilen[$v] = ['nr' => $v, 'name' => 'Vertreter ' . $v]; $sum[$v] = ['kunden' => 0, 'monat' => [0, 0], 'vjMonat' => [0, 0], 'j365' => [0, 0], 'v365' => [0, 0], 'signale' => array_fill_keys(CRM_COCKPIT_ARTEN, 0)]; }
            if (!empty($c['active'])) $sum[$v]['kunden']++;
            if (!$z) continue;
            foreach (['monat', 'vjMonat', 'j365', 'v365'] as $w) { $sum[$v][$w][0] += $z['w'][$w][0]; $sum[$v][$w][1] += $z['w'][$w][1]; }
            foreach ($z['signale'] as $s) $sum[$v]['signale'][$s['art']]++;
        }
    }
    $out = [];
    foreach ($zeilen as $nr => $zl) {
        $s = $sum[$nr];
        if ($nr === '_' && $s['kunden'] === 0 && $s['j365'] === [0, 0]) continue;
        $out[] = $zl + ['kunden' => $s['kunden'], 'monat' => crm_um($s['monat'], $r), 'vjMonat' => crm_um($s['vjMonat'], $r), 'j365' => crm_um($s['j365'], $r),
                        'v365' => crm_um($s['v365'], $r), 'signale' => $s['signale']];
    }
    return $out;
}

/* Übersicht im Kunden-Pop-up: Umsatz und Menge (365 Tage mit Vorjahr), Monate mit Vorjahr, letzter Kauf, Rhythmus, Preisniveau
   (nur mit € und kg), Top-Artikel, Signale und „Auffällig bei Artikeln“. Interessenten und Kunden ohne Nummer: keine Umsätze. */
function crm_kunde_umsatz(array $me, string $key): array
{
    $r = crm_zahlrechte($me);
    $c = crm_stammkunden()[$key] ?? null;
    $nr = $c ? trim((string)($c['nr'] ?? '')) : '';
    $o = ['ok' => true, 'key' => $key, 'rechte' => $r, 'stand' => null, 'von' => null, 'vorjahr' => null, 'kunde' => null];
    if ($nr === '') return $o;
    crm_kundenbild();
    $kb = kundenbild_kunde($nr);
    if ($kb === null) return $o;
    $o = array_merge($o, ['stand' => $kb['stand'], 'von' => $kb['von'], 'vorjahr' => $kb['vorjahr'] ?? null]);
    $k = $kb['kunde'];
    if ($k === null) return $o;
    $preis = $r['euro'] && $r['kg'];
    $o['kunde'] = [
        'w' => array_map(fn($w) => crm_um($w, $r), array_intersect_key($k['w'], array_flip(['j365', 'v365', 'j91', 'monat', 'vjMonat', 'jahr', 'vjJahr']))),
        'monate' => array_map(fn($m) => ['monat' => $m['monat'], 'jetzt' => crm_um($m['jetzt'], $r), 'vj' => crm_um($m['vj'], $r)], $k['monate']),
        'zuletzt' => $k['zuletzt'], 'kauftage' => $k['kauftage'], 'rhythmus' => $k['rhythmus'],
        'preisniveau' => $preis ? $k['preisniveau'] : null,
        'artikel' => array_map(fn($x) => ['nr' => $x['nr'], 'name' => $x['name'], 'fleischart' => $x['fleischart'], 'zuletzt' => $x['zuletzt'],
            'j365' => crm_um($x['j365'], $r), 'v365' => crm_um($x['v365'], $r),
            'preisAlle' => $preis && $x['alle'] ? (int)round($x['alle'][0] * 1000 / $x['alle'][1]) : null], $k['artikel']),
        'artikelGesamt' => $k['artikelGesamt'],
        'signale' => crm_zahlen_filtern($k['signale'], $r),
        'auffaellig' => crm_zahlen_filtern($k['auffaellig'], $r),
    ];
    return $o;
}
