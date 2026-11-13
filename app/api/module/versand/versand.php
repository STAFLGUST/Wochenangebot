<?php
declare(strict_types=1);
/* Modul Versand: Wochenangebot und Kundenangebote veröffentlichen und per E-Mail an Kunden senden (Oberfläche
   versand.intern, Seite app/module/versand/, Aktionen app/api/aktionen/versand.php; Auftrag des Inhabers 13.11.2026).

   Das Modul ist Oberfläche und Ablauf – es hat keine eigenen Dokumente und greift auf fremde nur über die Funktionen der
   Eigentümer zu (GR-101):
     Angebot      angebot_stand(), angebot_aenderungen(), angebot_veroeffentlichen() (lib/angebote.php),
                  wochenmail_*(), sonderposten_*(), mail_tpl_*() (lib/kundenmail.php)
     Verwaltung   customers_load() über die Funktionen oben (Kunden und ihre freigeschalteten Angebote)
     Plattform    protokoll_monat() für den Verlauf, mail_cfg()/require_mail() für das Postfach
   Rechte (GR-103): der Modulzugang versand.zugang gilt für jede Aktion (API-Einstieg, modul_zugang_durchsetzen); dazu
   angebot.veroeffentlichen (Veröffentlichen), wochenangebot.senden und sonderposten.senden (Senden, mit Bestätigung). Die
   Änderungsliste enthält Preise – nur mit Modulzugang Angebot. Empfänger mit Firma und Adresse nur mit dem Senden-Recht;
   Stand und Verlauf nennen nur Zahlen. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const VS_VERLAUF_MAX = 60;          // Einträge im Verlauf
const VS_VERLAUF_PAUSE = 900;       // Teile einer Sendung (je 10–20 Kunden) liegen höchstens so viele Sekunden auseinander

/* Was darf dieser Mitarbeiter im Modul? (nur für die Anzeige der Knöpfe – jede Aktion prüft selbst) */
function vs_rechte(array $me): array
{
    return ['veroeffentlichen' => may($me, 'angebot.veroeffentlichen'), 'woche' => may($me, 'wochenangebot.senden'),
            'sonderposten' => may($me, 'sonderposten.senden'), 'angebot' => modul_zugang_frei($me, 'angebot'),
            'bearbeiten' => modul_zugang_frei($me, 'angebot') && may($me, 'angebot.bearbeiten')];
}
/* Angebotswoche als Text-Bausteine (Montag bis Sonntag) */
function vs_woche(int $week, int $year): ?array
{
    if ($week < 1 || $week > 53 || $year < 2000) return null;
    $mo = (new DateTimeImmutable())->setISODate($year, $week);
    return ['week' => $week, 'year' => $year, 'von' => $mo->format('Y-m-d'), 'bis' => $mo->modify('+6 days')->format('Y-m-d')];
}
/* Stand für die Seite: Entwurf und veröffentlichtes Angebot, Zahl der Änderungen (gesamt, je Angebot, je Art – ohne Zeilen),
   Angebote der Woche mit Kunden und letztem Versand, Stand des Versands. Nur Zahlen und Namen der Angebote. */
function vs_stand(array $me): array
{
    $st = angebot_stand();
    $ae = angebot_aenderungen();
    unset($ae['zeilen']);
    $emp = wochenmail_empfaenger();
    $wk = $emp['woche'];
    // Je Angebot: Kunden, die die Wochen-Mail bekommen, wie viele sie für die veröffentlichte Woche schon haben, und der letzte
    // Versand überhaupt (Woche und Zeitpunkt aus dem Vermerk am Kunden) – dasselbe über alle Kunden
    $jeAngebot = []; $gesendet = 0; $letzter = null;
    $neuer = fn(?array $alt, array $w) => $alt === null || strcmp($w['t'], $alt['t']) > 0 ? $w : $alt;
    foreach ($emp['empfaenger'] as $c) {
        if ($c['gesendet'] !== '') $gesendet++;
        if ($c['wochenmail']) $letzter = $neuer($letzter, $c['wochenmail']);
        foreach ($c['angebote'] as $oid) {
            $jeAngebot[$oid]['kunden'] = ($jeAngebot[$oid]['kunden'] ?? 0) + 1;
            if ($c['gesendet'] !== '') $jeAngebot[$oid]['gesendet'] = ($jeAngebot[$oid]['gesendet'] ?? 0) + 1;
            if ($c['wochenmail']) $jeAngebot[$oid]['zuletzt'] = $neuer($jeAngebot[$oid]['zuletzt'] ?? null, $c['wochenmail']);
        }
    }
    $angebote = [];
    foreach ($st['angebote'] as $a) {
        $j = $jeAngebot[$a['id']] ?? [];
        $angebote[] = $a + ['kunden' => (int)($j['kunden'] ?? 0), 'gesendet' => (int)($j['gesendet'] ?? 0), 'zuletzt' => $j['zuletzt'] ?? null,
                            // Wochenangebot: Änderungen an Artikeln und Kopfdaten (gelten für alle Angebote) und Sichtbarkeit im Wochenangebot
                            'aenderungen' => (int)($ae['jeAngebot'][$a['id']] ?? 0) + ($a['std'] ? (int)($ae['jeAngebot'][''] ?? 0) : 0)];
    }
    $v = $st['veroeffentlicht']; $e = $st['entwurf'];
    return ['veroeffentlicht' => $v ? $v + ['woche' => vs_woche($v['week'], $v['year'])] : null,
            'entwurf' => $e ? $e + ['woche' => vs_woche($e['week'], $e['year'])] : null,
            'anwesend' => array_values(array_diff($st['anwesend'], [$me['name'] ?? ''])),
            'aenderungen' => $ae, 'angebote' => $angebote,
            'versand' => ['empfaenger' => count($emp['empfaenger']), 'gesendet' => $gesendet, 'ausgeschlossen' => count($emp['ausgeschlossen']), 'zuletzt' => $letzter,
                          'postfach' => (bool)mail_cfg() && (bool)mail_base_url()]];
}
/* Verlauf: Veröffentlichungen und Sendungen aus dem Protokoll des Plattformkerns (Vorgänge „publish“ und „mail“ mit den
   Schlüsseln …|woche bzw. …|restposten). Nur Zeitpunkt, Mitarbeiter, Art, Text und Anzahl – nie Firmen oder Adressen
   (die stehen in den Einzelheiten des Protokolls und bleiben dort). Die Teile einer Sendung werden zusammengezählt. */
function vs_verlauf(int $monate = 2): array
{
    $monate = max(1, min(PROTOKOLL_MONATE, $monate));
    $roh = [];
    for ($i = 0; $i > -$monate; $i--) {
        foreach (protokoll_monat(utc_monat($i)) as $e) {
            $a = (string)($e['a'] ?? '');
            if ($a === 'publish') { $roh[] = ['t' => (string)$e['t'], 'art' => 'veroeffentlicht', 'titel' => (string)$e['s'], 'von' => (string)($e['n'] ?? ''), 'u' => (string)($e['u'] ?? ''), 'ok' => 0, 'fehler' => 0]; continue; }
            if ($a !== 'mail' || empty($e['d']) || !is_array($e['d'])) continue;
            $k = (string)($e['d'][0]['k'] ?? '');
            $art = str_ends_with($k, '|woche') ? 'woche' : (str_ends_with($k, '|restposten') ? 'sonderposten' : '');
            if ($art === '') continue;
            $ok = 0; $bad = 0;
            foreach ($e['d'] as $d) { if (strpos((string)($d['to'] ?? ''), ' – ') === false) $ok++; else $bad++; }
            $titel = preg_match('/^(.*?) an \d+ Kunden versendet/u', (string)$e['s'], $m) ? $m[1] : ($art === 'woche' ? 'Wochenangebot' : 'Sonderposten');
            $roh[] = ['t' => (string)$e['t'], 'art' => $art, 'titel' => $titel, 'von' => (string)($e['n'] ?? ''), 'u' => (string)($e['u'] ?? ''), 'ok' => $ok, 'fehler' => $bad];
        }
    }
    usort($roh, fn($x, $y) => strcmp($x['t'], $y['t']));
    $out = [];
    foreach ($roh as $e) {
        $n = count($out) - 1;
        if ($e['art'] !== 'veroeffentlicht' && $n >= 0 && $out[$n]['art'] === $e['art'] && $out[$n]['titel'] === $e['titel'] && $out[$n]['u'] === $e['u']
            && strtotime($e['t']) - strtotime($out[$n]['t']) <= VS_VERLAUF_PAUSE) {
            $out[$n]['ok'] += $e['ok']; $out[$n]['fehler'] += $e['fehler']; $out[$n]['t'] = $e['t'];
            continue;
        }
        $out[] = $e;
    }
    $out = array_slice(array_reverse($out), 0, VS_VERLAUF_MAX);
    return array_map(function ($e) { unset($e['u']); return $e; }, $out);
}
/* Offene Punkte für „Heute für Sie“ auf dem Dashboard (lib/startseite.php): unveröffentlichte Änderungen und ein noch nicht
   versendetes Wochenangebot – jeweils nur, wenn der Mitarbeiter es auch erledigen darf */
function versand_startseite(array $me): array
{
    $out = [];
    $r = vs_rechte($me);
    if (!$r['veroeffentlichen'] && !$r['woche']) return $out;
    $st = vs_stand($me);
    $n = (int)$st['aenderungen']['anzahl'];
    $e = $st['entwurf']; $v = $st['veroeffentlicht'];
    if ($r['veroeffentlichen'] && $n > 0) $out[] = ['art' => 'heute', 'titel' => $n === 1 ? '1 Änderung nicht veröffentlicht' : "$n Änderungen nicht veröffentlicht",
        'detail' => 'Wochenangebot' . ($e ? ' KW ' . $e['week'] . '/' . $e['year'] : ''), 'datum' => '', 'ziel' => '', 'anzahl' => 1];
    if ($r['woche'] && $v && $n === 0 && $st['versand']['empfaenger'] > 0 && $st['versand']['gesendet'] === 0 && $st['versand']['postfach'])
        $out[] = ['art' => 'heute', 'titel' => 'KW ' . $v['week'] . ' noch nicht versendet', 'detail' => $st['versand']['empfaenger'] . ' Kunden bekommen das Wochenangebot per E-Mail',
                  'datum' => '', 'ziel' => '', 'anzahl' => 1];
    return $out;
}
