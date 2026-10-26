<?php
declare(strict_types=1);
/* Bereitschaft für den Ernstfall (Oberfläche: Modul Sicherheit; Dienst im Plattformkern, docs/plattform/modul-sicherheit.md §8).
   - Leitfaden: Schritte und Ansprechpartner für den Ernstfall (Administratoren pflegen ihn); während eines Notfalls abhakbar –
     wer, wann bleibt beim jeweiligen Notfall gespeichert.
   - Probealarm: Übung ohne jede Wirkung – Bereitschaftsprüfung (Empfänger, Vertretung, Zwei-Faktor, Ansprechpartner,
     Selbstaussperrung, Sicherung) und eine Test-Benachrichtigung an die Empfänger der Sicherheitsereignisse. Wer die Meldung
     sieht, bestätigt im Modul („gesehen“); die Reaktionszeit wird vermerkt.
   - Wochenbericht: Zusammenfassung der letzten 7 Tage per E-Mail an die Empfänger der Sicherheitsereignisse – automatisch einmal
     je Woche ab dem eingestellten Wochentag (angestoßen von der ersten Mitarbeiter-Anfrage, versendet nach der Antwort; kein
     Zeitplan auf dem Server nötig), jederzeit auf Knopfdruck. Der erste automatische Bericht kommt in der Woche nach dem Einschalten.
   Dokument „sicherheit-bereitschaft“: {leitfaden{schritte[], kontakte[], hinweis, geaendert, von}, haken{<Notfall seit>: {<Schritt>: {t, name}}},
   proben[{id, t, uid, von, vonName, punkte[], mail{}, quittiert[]}], bericht{an, tag, woche, verlauf[]}}.
   Die Wirkung des Notfalls selbst liegt in lib/notfall.php; dieser Dienst ändert dort nichts. Rechte prüfen die Aktionen. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const BEREIT_MAX_SCHRITTE = 15;
const BEREIT_MAX_KONTAKTE = 10;
const BEREIT_HAKEN_MAX = 20;          // abgehakte Leitfäden der letzten Notfälle
const BEREIT_PROBEN_MAX = 20;
const BEREIT_PROBE_PAUSE = 300;       // Sekunden zwischen zwei Probealarmen
const BEREIT_PROBE_OFFEN = 86400;     // so lange lässt sich ein Probealarm als „gesehen“ bestätigen
const BERICHT_AB_STUNDE = 7;          // automatischer Wochenbericht frühestens ab 7 Uhr (Ortszeit)
const BERICHT_VERLAUF_MAX = 12;
const BERICHT_TAGE = ['', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];

/* Vorlage des Leitfadens (gilt, bis ein Administrator eigene Schritte speichert) */
const LEITFADEN_STANDARD = [
    ['id' => 'ausloesen', 'titel' => 'Notfall auslösen', 'text' => 'Bei Verdacht sofort den Notfallmodus auslösen – lieber einmal zu früh. Kunden sehen dann eine neutrale Wartung, Mitarbeiter ohne Administratorrolle sind ausgesperrt.'],
    ['id' => 'informieren', 'titel' => 'Ansprechpartner informieren', 'text' => 'Geschäftsführung und IT-Dienstleister anrufen (Ansprechpartner unten). Nicht nur per E-Mail – das Postfach könnte betroffen sein.'],
    ['id' => 'lage', 'titel' => 'Lage erfassen', 'text' => 'Ereignisse, auffällige Adressen und Dateiprüfung ansehen. Zeitpunkte, Konten und Adressen notieren, nichts löschen.'],
    ['id' => 'konten', 'titel' => 'Konten absichern', 'text' => 'Betroffene Konten sperren bzw. Passwörter zurücksetzen und Sitzungen beenden. Verdächtige Adressen sperren.'],
    ['id' => 'daten', 'titel' => 'Daten prüfen', 'text' => 'Letzte Datensicherung prüfen. Bei veränderten Daten die Wiederherstellung mit dem IT-Dienstleister planen.'],
    ['id' => 'meldepflicht', 'titel' => 'Meldepflicht prüfen', 'text' => 'Sind personenbezogene Daten betroffen, kann eine Meldung an die Datenschutz-Aufsichtsbehörde binnen 72 Stunden nötig sein (Art. 33 DSGVO) – mit dem Datenschutzbeauftragten klären.'],
    ['id' => 'beheben', 'titel' => 'Ursache beheben', 'text' => 'Lücke schließen (Updates, Zugänge, Einstellungen), bevor der Betrieb wieder startet.'],
    ['id' => 'beenden', 'titel' => 'Notfall beenden und nachbereiten', 'text' => 'Notfall beenden (nur Administratoren), Ursache und Maßnahmen als Notiz festhalten, Leitfaden bei Bedarf anpassen.'],
];

function bereit_dok(): array { $d = store_read('sicherheit-bereitschaft'); return is_array($d) ? $d : []; }
/* Ändern unter Sperre: $fn(array &$d) – Rückgabe von $fn wird weitergereicht */
function bereit_aendern(callable $fn)
{
    return with_lock('sicherheit-bereitschaft', function () use ($fn) {
        $d = bereit_dok();
        $r = $fn($d);
        store_write('sicherheit-bereitschaft', $d);
        return $r;
    });
}

/* ---------- Leitfaden ---------- */
function leitfaden(): array
{
    $l = is_array(bereit_dok()['leitfaden'] ?? null) ? bereit_dok()['leitfaden'] : [];
    $eigen = array_values(array_filter((array)($l['schritte'] ?? []), function ($s) { return is_array($s) && isset($s['id'], $s['titel']); }));
    $kontakte = array_values(array_filter((array)($l['kontakte'] ?? []), 'is_array'));
    return ['schritte' => $eigen ?: LEITFADEN_STANDARD, 'standard' => !$eigen, 'kontakte' => $kontakte, 'hinweis' => (string)($l['hinweis'] ?? ''),
            'geaendert' => $l['geaendert'] ?? null, 'von' => (string)($l['von'] ?? ''), 'vorlage' => LEITFADEN_STANDARD];
}
/* Speichern (Administrator). $b: schritte[{id?, titel, text}] oder standard = true, kontakte[{rolle, name, telefon, email}], hinweis */
function leitfaden_speichern(array $me, array $b): array
{
    $alt = leitfaden();
    $schritte = [];
    if (empty($b['standard'])) {
        $ids = [];
        foreach (array_slice(is_array($b['schritte'] ?? null) ? $b['schritte'] : [], 0, BEREIT_MAX_SCHRITTE + 1) as $s) {
            if (!is_array($s)) continue;
            $titel = modul_text((string)($s['titel'] ?? ''), 80);
            $text = modul_text((string)($s['text'] ?? ''), 400);
            if ($titel === '' && $text === '') continue;
            if ($titel === '') fail('Jeder Schritt braucht eine Überschrift.', 422);
            $id = (string)($s['id'] ?? '');
            if (!preg_match('/^[a-z0-9-]{1,24}$/D', $id) || isset($ids[$id])) $id = 's' . bin2hex(random_bytes(4));
            $ids[$id] = true;
            $schritte[] = ['id' => $id, 'titel' => $titel, 'text' => $text];
        }
        if (!$schritte) fail('Bitte mindestens einen Schritt angeben (oder die Vorlage verwenden).', 422);
        if (count($schritte) > BEREIT_MAX_SCHRITTE) fail('Höchstens ' . BEREIT_MAX_SCHRITTE . ' Schritte.', 422);
    }
    $kontakte = [];
    foreach (array_slice(is_array($b['kontakte'] ?? null) ? $b['kontakte'] : [], 0, BEREIT_MAX_KONTAKTE + 1) as $k) {
        if (!is_array($k)) continue;
        $x = ['rolle' => modul_text((string)($k['rolle'] ?? ''), 60), 'name' => modul_text((string)($k['name'] ?? ''), 80),
              'telefon' => modul_text((string)($k['telefon'] ?? ''), 40), 'email' => modul_text((string)($k['email'] ?? ''), 120)];
        if (implode('', $x) === '') continue;
        if ($x['name'] === '' && $x['rolle'] === '') fail('Bitte für jeden Ansprechpartner Name oder Aufgabe angeben.', 422);
        if ($x['telefon'] === '' && $x['email'] === '') fail('Bitte für „' . ($x['name'] ?: $x['rolle']) . '“ Telefon oder E-Mail angeben.', 422);
        if ($x['telefon'] !== '' && !preg_match('#^[0-9 +()/.\-]{3,40}$#D', $x['telefon'])) fail('„' . $x['telefon'] . '“ ist keine gültige Telefonnummer.', 422);
        if ($x['email'] !== '' && filter_var($x['email'], FILTER_VALIDATE_EMAIL) === false) fail('„' . $x['email'] . '“ ist keine gültige E-Mail-Adresse.', 422);
        $kontakte[] = $x;
    }
    if (count($kontakte) > BEREIT_MAX_KONTAKTE) fail('Höchstens ' . BEREIT_MAX_KONTAKTE . ' Ansprechpartner.', 422);
    $hinweis = modul_text((string)($b['hinweis'] ?? ''), 500);
    bereit_aendern(function (array &$d) use ($schritte, $kontakte, $hinweis, $me) {
        $d['leitfaden'] = ['schritte' => $schritte, 'kontakte' => $kontakte, 'hinweis' => $hinweis, 'geaendert' => now(), 'von' => (string)$me['name']];
    });
    $neu = leitfaden();
    $n = function (array $l) { return $l['standard'] ? 'Vorlage (' . count($l['schritte']) . ' Schritte)' : count($l['schritte']) . ' eigene Schritte'; };
    audit('notfall', 'Notfall-Leitfaden geändert', [
        ['k' => 'leitfaden|schritte', 'code' => '', 'name' => 'Leitfaden', 'f' => 'Schritte', 'from' => $n($alt), 'to' => $n($neu)],
        ['k' => 'leitfaden|kontakte', 'code' => '', 'name' => 'Leitfaden', 'f' => 'Ansprechpartner', 'from' => (string)count($alt['kontakte']), 'to' => (string)count($neu['kontakte'])]]);
    return $neu;
}
/* Abgehakte Schritte eines Notfalls (Schlüssel: Beginn des Notfalls) */
function leitfaden_haken_fuer(?string $seit): array
{
    if (!$seit) return [];
    $h = bereit_dok()['haken'][$seit] ?? [];
    return is_array($h) ? $h : [];
}
/* Schritt im laufenden Notfall abhaken bzw. zurücknehmen ($b: schritt, erledigt) */
function leitfaden_haken(array $me, array $b): array
{
    $n = notfall();
    if (!$n) fail('Abhaken ist nur während eines Notfalls möglich.', 409);
    $id = (string)($b['schritt'] ?? '');
    if (!in_array($id, array_column(leitfaden()['schritte'], 'id'), true)) fail('Unbekannter Schritt.', 422);
    $seit = (string)($n['seit'] ?? '');
    $an = !empty($b['erledigt']);
    bereit_aendern(function (array &$d) use ($seit, $id, $an, $me) {
        $h = is_array($d['haken'] ?? null) ? $d['haken'] : [];
        $x = is_array($h[$seit] ?? null) ? $h[$seit] : [];
        if ($an) $x[$id] = $x[$id] ?? ['t' => now(), 'name' => (string)$me['name']]; else unset($x[$id]);
        $h[$seit] = $x;
        if (count($h) > BEREIT_HAKEN_MAX) { ksort($h); $h = array_slice($h, -BEREIT_HAKEN_MAX, null, true); }
        $d['haken'] = $h;
    });
    return leitfaden_haken_fuer($seit);
}

/* ---------- Probealarm ---------- */
function bereit_proben(): array
{
    return array_values(array_filter((array)(bereit_dok()['proben'] ?? []), 'is_array'));
}
/* Bereitschaftsprüfung: [{k, stufe ok|warn|bad|info, titel, text, hinweis}] */
function probe_pruefung(): array
{
    $p = [];
    $add = function (string $k, string $stufe, string $titel, string $text, string $hinweis = '') use (&$p) { $p[] = compact('k', 'stufe', 'titel', 'text', 'hinweis'); };
    $to = notify_targets('sicherheit', true);
    $cfg = mail_cfg();
    if (!$to) $add('meldung', 'bad', 'Benachrichtigung im Ernstfall', 'Keine Empfänger für Sicherheitsereignisse eingetragen – ein Notfall würde niemandem gemeldet.', 'Verwaltung → E-Mail → Benachrichtigungen → Sicherheitsereignisse.');
    elseif (!$cfg) $add('meldung', 'bad', 'Benachrichtigung im Ernstfall', 'Postfach für den E-Mail-Versand nicht eingerichtet.', 'Verwaltung → E-Mail → Postfach.');
    else $add('meldung', 'ok', 'Benachrichtigung im Ernstfall', 'an ' . implode(', ', $to));
    $users = array_values(array_filter(users_load(), function ($u) { return !empty($u['active']) && nutzer_hat_zugang($u); }));
    $admins = array_values(array_filter($users, function ($u) { return ($u['role'] ?? '') === 'admin'; }));
    $ausloeser = array_filter($users, function ($u) { return ($u['role'] ?? '') === 'admin' || may($u, 'sicherheit.notfall'); });
    $add('ausloeser', count($ausloeser) >= 2 ? 'ok' : 'warn', 'Wer den Notfall auslösen kann', count($ausloeser) === 1 ? 'nur eine Person' : count($ausloeser) . ' Personen',
         count($ausloeser) >= 2 ? '' : 'Mindestens eine Vertretung mit dem Recht „Notfall auslösen“ einrichten (Verwaltung → Rollen & Rechte).');
    $add('beender', count($admins) >= 2 ? 'ok' : 'warn', 'Wer den Notfall beenden kann', count($admins) === 1 ? 'nur ein Administrator' : count($admins) . ' Administratoren',
         count($admins) >= 2 ? '' : 'Beenden können nur Administratoren – ohne Vertretung bleibt ein Notfall bei Abwesenheit bestehen (Rückweg: deploy/notfall-aus.sh).');
    $ohne = array_filter($admins, function ($u) { return !has_second_factor($u) && (string)($u['oidcSub'] ?? '') === ''; });
    $add('zweifaktor', $ohne ? 'bad' : 'ok', 'Administratoren mit zweitem Faktor', $ohne ? count($ohne) . ' ohne zweiten Faktor: ' . implode(', ', array_map(function ($u) { return $u['username']; }, array_slice($ohne, 0, 5))) : 'alle geschützt',
         $ohne ? 'Einmalcode oder Passkey einrichten lassen – ein übernommenes Administratorkonto kann den Notfall beenden.' : '');
    $k = count(leitfaden()['kontakte']);
    $add('kontakte', $k ? 'ok' : 'warn', 'Ansprechpartner im Leitfaden', $k ? ($k === 1 ? '1 Ansprechpartner' : $k . ' Ansprechpartner') : 'keine eingetragen', $k ? '' : 'Im Leitfaden Telefonnummern von Geschäftsführung und IT-Dienstleister hinterlegen.');
    $ip = client_ip();
    $add('selbstsperre', fw_erlaubt($ip) ? 'ok' : 'warn', 'Schutz vor Selbstaussperrung', fw_erlaubt($ip) ? 'Ihre Adresse wird von der Firewall nie gesperrt' : 'Die Notfall-Firewall sperrt schon nach dem ersten Angriffsmuster – auch Ihre Adresse ' . $ip,
         fw_erlaubt($ip) ? '' : 'Büroadresse unter Firewall → „nie sperren“ eintragen. Rückweg auf dem Server: deploy/notfall-aus.sh.');
    $s = store_read('sicherung');
    $alt = is_array($s) && !empty($s['t']) ? (time() - (strtotime((string)$s['t']) ?: 0)) / 3600 : null;
    if ($alt === null) $add('sicherung', 'warn', 'Datensicherung', 'noch keine automatische Sicherung', 'Tägliche Sicherung einrichten (deploy/sicherung-einrichten.sh).');
    else $add('sicherung', empty($s['ok']) || $alt > 48 ? 'bad' : 'ok', 'Datensicherung', empty($s['ok']) ? 'letzte Sicherung fehlgeschlagen' : ($alt > 48 ? 'älter als 2 Tage' : 'aktuell (' . date('d.m.Y, H:i', strtotime((string)$s['t'])) . ' Uhr)'),
              empty($s['ok']) || $alt > 48 ? 'Sicherung prüfen – im Ernstfall ist sie der Weg zurück.' : '');
    if (konten_eingerichtet()) $add('zentral', 'ok', 'Zentrale Anmeldung', 'Sitzungen bei Keycloak lassen sich im Notfall beenden');
    elseif (oidc_modus()) $add('zentral', 'warn', 'Zentrale Anmeldung', 'Kontenverwaltung nicht eingerichtet – Keycloak-Sitzungen lassen sich im Notfall nicht beenden', 'deploy/anmeldung/konten.sh realm-aktualisieren und Neustart der Anwendung.');
    else $add('zentral', 'info', 'Zentrale Anmeldung', 'auf diesem Host nicht verwendet');
    return $p;
}
/* Probealarm auslösen ($me: sicherheit.notfall oder Administrator). Ändert nichts außer dem Übungsverlauf. */
function probe_ausloesen(array $me): array
{
    if (notfall_aktiv()) fail('Während eines Notfalls ist kein Probealarm möglich.', 409);
    $letzte = bereit_proben()[0] ?? null;
    if ($letzte && strtotime((string)$letzte['t']) > time() - BEREIT_PROBE_PAUSE) fail('Der letzte Probealarm ist noch keine 5 Minuten her.', 429);
    $punkte = probe_pruefung();
    $wertbar = array_values(array_filter($punkte, function ($x) { return $x['stufe'] !== 'info'; }));
    $ok = count(array_filter($wertbar, function ($x) { return $x['stufe'] === 'ok'; }));
    $t = now();
    $to = notify_targets('sicherheit', true);
    $mail = ['an' => count($to), 'ok' => 0, 'fehler' => ''];
    if ($to && mail_cfg()) {
        $offen = array_values(array_filter($punkte, function ($x) { return in_array($x['stufe'], ['warn', 'bad'], true); }));
        $zeilen = [['Ausgelöst von', $me['name'] . ' (' . $me['username'] . ')'], ['Zeit', date('d.m.Y, H:i', strtotime($t)) . ' Uhr'],
                   ['Bereitschaft', $ok . ' von ' . count($wertbar) . ' Prüfpunkten in Ordnung']];
        foreach (array_slice($offen, 0, 5) as $x) $zeilen[] = [$x['titel'], $x['text']];
        $inhalt = bereit_mail('PROBEALARM (Übung) – keine Wirkung',
            'dies ist ein Probealarm. Es wurde nichts gesperrt und nichts geändert. Bitte bestätigen Sie in der Sicherheitszentrale unter „Notfall“ mit „Probealarm gesehen“, dass die Meldung angekommen ist – so wird die Reaktionszeit festgehalten.',
            [['titel' => 'Übung', 'zeilen' => $zeilen]], 'Notfall');
        $res = notify_send('sicherheit', $to, [], 0, false, 'Probealarm', $inhalt);
        $mail['ok'] = count(array_filter($res, function ($r) { return $r['ok']; }));
        foreach ($res as $r) if (!$r['ok']) { $mail['fehler'] = mb_substr((string)$r['error'], 0, 160); break; }
    } else $mail['fehler'] = $to ? 'Postfach nicht eingerichtet' : 'keine Empfänger eingetragen';
    $e = ['id' => bin2hex(random_bytes(6)), 't' => $t, 'uid' => (string)$me['id'], 'von' => (string)$me['username'], 'vonName' => (string)$me['name'],
          'punkte' => $punkte, 'ok' => $ok, 'gesamt' => count($wertbar), 'mail' => $mail, 'quittiert' => []];
    bereit_aendern(function (array &$d) use ($e) {
        $l = array_values(array_filter((array)($d['proben'] ?? []), 'is_array'));
        array_unshift($l, $e);
        $d['proben'] = array_slice($l, 0, BEREIT_PROBEN_MAX);
    });
    audit('notfall', 'Probealarm durchgeführt (Übung ohne Wirkung)', [['k' => 'probe', 'code' => '', 'name' => 'Probealarm', 'f' => 'Bereitschaft', 'from' => '',
        'to' => $ok . ' von ' . count($wertbar) . ' in Ordnung · Meldung an ' . $mail['ok'] . ' von ' . $mail['an'] . ' Empfängern']]);
    return $e;
}
/* Offener Probealarm für $me (jünger als 24 Stunden, nicht selbst ausgelöst, noch nicht bestätigt) */
function probe_offen(array $me): ?array
{
    $p = bereit_proben()[0] ?? null;
    if (!$p || strtotime((string)$p['t']) < time() - BEREIT_PROBE_OFFEN || (string)$p['uid'] === (string)$me['id']) return null;
    foreach ((array)$p['quittiert'] as $q) if ((string)($q['uid'] ?? '') === (string)$me['id']) return null;
    return $p;
}
/* „Probealarm gesehen“: Reaktionszeit vermerken */
function probe_quittieren(array $me, string $id): array
{
    $r = bereit_aendern(function (array &$d) use ($me, $id) {
        $l = array_values(array_filter((array)($d['proben'] ?? []), 'is_array'));
        $p = $l[0] ?? null;
        if (!$p || (string)$p['id'] !== $id || strtotime((string)$p['t']) < time() - BEREIT_PROBE_OFFEN) fail('Dieser Probealarm kann nicht mehr bestätigt werden.', 409);
        if ((string)$p['uid'] === (string)$me['id']) fail('Den eigenen Probealarm müssen Sie nicht bestätigen.', 409);
        foreach ((array)$p['quittiert'] as $q) if ((string)($q['uid'] ?? '') === (string)$me['id']) return [$p, null];
        $q = ['uid' => (string)$me['id'], 'name' => (string)$me['name'], 't' => now(), 'sek' => max(0, time() - (int)strtotime((string)$p['t']))];
        $p['quittiert'][] = $q;
        $l[0] = $p;
        $d['proben'] = $l;
        return [$p, $q];
    });
    [$p, $q] = $r;
    if ($q) audit('notfall', 'Probealarm gesehen (nach ' . bereit_dauer((int)$q['sek']) . ')');
    return $p;
}
function bereit_dauer(int $s): string
{
    return $s >= 3600 ? intdiv($s, 3600) . ' Std. ' . intdiv($s % 3600, 60) . ' Min.' : ($s >= 60 ? intdiv($s, 60) . ' Min.' : $s . ' Sek.');
}

/* ---------- Wochenbericht ---------- */
function bericht_einstellungen(): array
{
    $b = is_array(bereit_dok()['bericht'] ?? null) ? bereit_dok()['bericht'] : [];
    $tag = (int)($b['tag'] ?? 1);
    return ['an' => !array_key_exists('an', $b) || !empty($b['an']), 'tag' => $tag >= 1 && $tag <= 7 ? $tag : 1, 'woche' => (string)($b['woche'] ?? ''),
            'verlauf' => array_slice(array_values(array_filter((array)($b['verlauf'] ?? []), 'is_array')), 0, BERICHT_VERLAUF_MAX)];
}
/* Anzeige für das Modul: Einstellungen, Empfänger, nächster automatischer Versand */
function bericht_anzeige(): array
{
    $e = bericht_einstellungen();
    $e['empfaenger'] = notify_targets('sicherheit', true);
    $e['postfach'] = (bool)mail_cfg();
    $e['tage'] = BERICHT_TAGE;
    $e['naechster'] = $e['an'] ? bericht_naechster($e) : null;
    return $e;
}
/* Nächster automatischer Versand (Ortszeit, ISO 8601): in dieser Woche schon vermerkt → eine Woche später, sonst der
   Berichtstag dieser Woche bzw. – wenn der schon vorbei ist – mit der nächsten Mitarbeiter-Anfrage */
function bericht_naechster(array $e): string
{
    $jetzt = new DateTimeImmutable();
    $ziel = $jetzt->modify('monday this week')->setTime(BERICHT_AB_STUNDE, 0)->modify('+' . ($e['tag'] - 1) . ' days');
    if ($e['woche'] === $jetzt->format('o-\WW')) $ziel = $ziel->modify('+7 days');
    elseif ($ziel < $jetzt) $ziel = $jetzt;
    return $ziel->format(DATE_ATOM);
}
function bericht_speichern(array $me, array $b): array
{
    $an = !empty($b['an']);
    $tag = (int)($b['tag'] ?? 1);
    if ($tag < 1 || $tag > 7) fail('Ungültiger Wochentag.', 422);
    $alt = bericht_einstellungen();
    bereit_aendern(function (array &$d) use ($an, $tag, $alt) {
        $x = is_array($d['bericht'] ?? null) ? $d['bericht'] : [];
        // Einschalten: der erste automatische Bericht kommt in der folgenden Woche (keine Überraschungs-Mail beim Einschalten)
        if ($an && (!$alt['an'] || empty($x['woche']))) $x['woche'] = date('o-\WW');
        $x['an'] = $an; $x['tag'] = $tag;
        $d['bericht'] = $x;
    });
    $ch = [];
    if ($alt['an'] !== $an) $ch[] = ['k' => 'bericht|an', 'code' => '', 'name' => 'Wochenbericht', 'f' => 'Versand', 'from' => $alt['an'] ? 'an' : 'aus', 'to' => $an ? 'an' : 'aus'];
    if ($alt['tag'] !== $tag) $ch[] = ['k' => 'bericht|tag', 'code' => '', 'name' => 'Wochenbericht', 'f' => 'Wochentag', 'from' => BERICHT_TAGE[$alt['tag']], 'to' => BERICHT_TAGE[$tag]];
    if ($ch) audit('security', 'Wochenbericht der Sicherheit ' . ($an ? 'eingestellt' : 'ausgeschaltet'), $ch);
    return bericht_anzeige();
}

/* Inhalt des Berichts (letzte 7 Tage) – Abschnitte mit Zeilen [Bezeichnung, Wert, Stufe] und Listen; eine Quelle für E-Mail und Modul */
function bericht_daten(): array
{
    $bis = time(); $von = $bis - 7 * 86400;
    $users = users_load();
    $log = sec_log_entries(7);
    $zaehl = function (array $arten) use ($log) { return count(array_filter($log, function ($e) use ($arten) { return in_array($e['a'] ?? '', $arten, true); })); };
    $stufe = function (array $zeilen): string { $s = array_column($zeilen, 2); return in_array('bad', $s, true) ? 'bad' : (in_array('warn', $s, true) ? 'warn' : 'ok'); };
    $ab = [];

    // Gesamtbild: Konfigurationsprüfung
    $cf = sec_config_checks($users);
    $warn = array_values(array_filter($cf, function ($c) { return in_array($c['level'], ['warn', 'bad'], true); }));
    $nBad = count(array_filter($cf, function ($c) { return $c['level'] === 'bad'; }));
    $ab[] = ['k' => 'gesamt', 'titel' => 'Konfigurationsprüfung', 'stufe' => $nBad ? 'bad' : ($warn ? 'warn' : 'ok'),
             'zeilen' => [['Prüfungen in Ordnung', count(array_filter($cf, function ($c) { return $c['level'] === 'ok'; })) . ' von ' . count(array_filter($cf, function ($c) { return $c['level'] !== 'info'; })), $nBad ? 'bad' : ($warn ? 'warn' : 'ok')]],
             'liste' => array_map(function ($c) { return ($c['level'] === 'bad' ? 'Kritisch: ' : 'Hinweis: ') . $c['title'] . ' – ' . $c['text']; }, array_slice($warn, 0, 8))];

    // Anmeldungen
    $fehlM = $zaehl(['login_fail']); $fehlK = $zaehl(['kunde_login_fail']); $fehlR = $zaehl(['reauth_fail']);
    $gesperrt = count(array_filter($users, function ($u) { return (int)($u['lockedUntil'] ?? 0) > time(); }));
    $z = [['Fehlanmeldungen Mitarbeiter', (string)$fehlM, $fehlM >= 20 ? 'bad' : ($fehlM >= 5 ? 'warn' : 'ok')],
          ['Fehlanmeldungen Kunden', (string)$fehlK, $fehlK >= 50 ? 'bad' : ($fehlK >= 10 ? 'warn' : 'ok')],
          ['Fehlgeschlagene Passwortbestätigungen', (string)$fehlR, $fehlR >= 5 ? 'warn' : 'ok'],
          ['Erfolgreiche Anmeldungen (Anwendung)', (string)$zaehl(['login', 'kunde_login']), 'info'],
          ['Zugänge jetzt gesperrt', (string)$gesperrt, $gesperrt ? 'warn' : 'ok']];
    $ips = array_map(function ($x) { return $x['ip'] . ' – ' . $x['n'] . ' Fehlversuche' . ($x['cc'] ? ' (' . $x['cc'] . ')' : '') . ($x['blocked'] ? ', gesperrt' : ''); }, array_slice(sec_top_ips($log), 0, 5));
    $ab[] = ['k' => 'anmeldung', 'titel' => 'Anmeldungen', 'stufe' => $stufe($z), 'zeilen' => $z, 'liste' => $ips,
             'hinweis' => oidc_modus() || konten_eingerichtet() ? 'Mitarbeiter melden sich über die zentrale Anmeldung (Keycloak) an; deren Fehlversuche zählt Keycloak.' : ''];

    // Firewall
    $fw = fw_zahlen(7 * 86400);
    $gesperrtAdr = (int)(fw_status()['zahlen']['gesperrteAdressen'] ?? 0);
    $F = fw();
    $z = [['Angriffsmuster erkannt', (string)$fw['angriffe'], $fw['angriffe'] >= 100 ? 'warn' : 'ok'],
          ['Anfragen gesperrter Adressen abgewiesen', (string)$fw['abgewiesen'], 'info'],
          ['Adressen jetzt gesperrt', (string)$gesperrtAdr, 'info'],
          ['Firewall', ($F['waf'] ?? '') === 'sperren' ? 'sperrt' : (($F['waf'] ?? '') === 'protokoll' ? 'protokolliert nur' : 'aus'), ($F['waf'] ?? '') === 'sperren' ? 'ok' : (($F['waf'] ?? '') === 'aus' ? 'bad' : 'warn')]];
    $ab[] = ['k' => 'firewall', 'titel' => 'Firewall', 'stufe' => $stufe($z), 'zeilen' => $z, 'liste' => []];

    // Zugänge
    $aktiv = array_values(array_filter($users, function ($u) { return !empty($u['active']) && nutzer_hat_zugang($u); }));
    $admins = array_filter($aktiv, function ($u) { return ($u['role'] ?? '') === 'admin'; });
    $ohne = array_filter($aktiv, function ($u) { return !has_second_factor($u) && (string)($u['oidcSub'] ?? '') === ''; });
    $ung = sec_ungenutzt(SEC_UNGENUTZT_TAGE, $users)['konten'];
    $aend = sec_ereignisse(7, 'konten', '', 50);
    $z = [['Aktive Zugänge', (string)count($aktiv), 'info'], ['Administratoren', (string)count($admins), count($admins) > 3 ? 'warn' : 'ok'],
          ['Ohne zweiten Faktor (eigene Anmeldung)', (string)count($ohne), array_filter($ohne, function ($u) { return ($u['role'] ?? '') === 'admin'; }) ? 'bad' : ($ohne ? 'warn' : 'ok')],
          ['Seit ' . SEC_UNGENUTZT_TAGE . ' Tagen nicht angemeldet', (string)count($ung), $ung ? 'warn' : 'ok'],
          ['Änderungen an Zugängen und Rollen', (string)count($aend['ereignisse']), 'info']];
    $liste = array_map(function ($e) { return date('d.m., H:i', strtotime((string)$e['t'])) . ' Uhr · ' . $e['s'] . ($e['n'] !== '' ? ' (' . $e['n'] . ')' : ''); }, array_slice($aend['ereignisse'], 0, 6));
    foreach (array_slice($ung, 0, 5) as $u) $liste[] = 'Ungenutzt: ' . $u['name'] . ' (' . $u['username'] . ') – ' . ($u['nie'] ? 'nie angemeldet' : 'zuletzt vor ' . $u['tage'] . ' Tagen');
    $ab[] = ['k' => 'konten', 'titel' => 'Zugänge', 'stufe' => $stufe($z), 'zeilen' => $z, 'liste' => $liste];

    // Notfall und Übungen
    $n = notfall();
    $nf = array_values(array_filter(notfall_verlauf(), function ($v) use ($von) { return strtotime((string)($v['seit'] ?? '')) >= $von; }));
    $proben = array_values(array_filter(bereit_proben(), function ($p) use ($von) { return strtotime((string)$p['t']) >= $von; }));
    $alleProben = bereit_proben();
    $letzteProbe = $alleProben[0]['t'] ?? null;
    $lf = leitfaden();
    $z = [['Notfallmodus', $n ? 'aktiv seit ' . date('d.m., H:i', strtotime((string)$n['seit'])) . ' Uhr' : 'nicht aktiv', $n ? 'bad' : 'ok'],
          ['Notfälle in dieser Woche', (string)(count($nf) + ($n && strtotime((string)$n['seit']) >= $von ? 1 : 0)), $nf ? 'warn' : 'ok'],
          ['Letzter Probealarm', $letzteProbe ? date('d.m.Y', strtotime((string)$letzteProbe)) : 'noch keiner', !$letzteProbe || strtotime((string)$letzteProbe) < $bis - 120 * 86400 ? 'warn' : 'ok'],
          ['Ansprechpartner im Leitfaden', (string)count($lf['kontakte']), $lf['kontakte'] ? 'ok' : 'warn']];
    $liste = array_map(function ($v) { return 'Notfall ' . date('d.m., H:i', strtotime((string)$v['seit'])) . ' Uhr: ' . $v['grund'] . ' (beendet von ' . $v['beendetVon'] . ')'; }, $nf);
    foreach ($proben as $p) $liste[] = 'Probealarm ' . date('d.m., H:i', strtotime((string)$p['t'])) . ' Uhr von ' . $p['vonName'] . ': ' . $p['ok'] . ' von ' . $p['gesamt'] . ' in Ordnung, ' . count((array)$p['quittiert']) . ' Bestätigungen';
    $ab[] = ['k' => 'notfall', 'titel' => 'Notfall und Übungen', 'stufe' => $stufe($z), 'zeilen' => $z, 'liste' => $liste];

    // Betrieb: Dateiprüfung, Sicherung, Bereitstellung
    $ip = integritaet_stand(false)['result'];
    $s = store_read('sicherung');
    $dep = store_read('deployment');
    $salt = is_array($s) && !empty($s['t']) ? (time() - (strtotime((string)$s['t']) ?: 0)) / 3600 : null;
    $z = [['Dateiprüfung', !$ip ? 'noch keine Prüfung' : ($ip['counts']['critical'] ?? 0 ? $ip['counts']['critical'] . ' kritisch' : (($ip['counts']['warnings'] ?? 0) ? $ip['counts']['warnings'] . ' Warnungen' : 'unauffällig')) . ($ip ? ' (' . date('d.m., H:i', strtotime((string)$ip['ranAt'])) . ' Uhr)' : ''),
           !$ip ? 'warn' : (($ip['counts']['critical'] ?? 0) ? 'bad' : (($ip['counts']['warnings'] ?? 0) ? 'warn' : 'ok'))],
          ['Datensicherung', $salt === null ? 'keine' : (empty($s['ok']) ? 'fehlgeschlagen' : date('d.m., H:i', strtotime((string)$s['t'])) . ' Uhr'), $salt === null ? 'warn' : (empty($s['ok']) || $salt > 48 ? 'bad' : 'ok')],
          ['Bereitstellung', is_array($dep) && !empty($dep['t']) ? substr((string)($dep['sha'] ?? ''), 0, 7) . ' · ' . date('d.m.Y', strtotime((string)$dep['t'])) . (empty($dep['ok']) ? ' (fehlgeschlagen)' : '') : 'ohne Freigabe', is_array($dep) && !empty($dep['t']) ? (empty($dep['ok']) ? 'bad' : 'ok') : 'warn']];
    $ab[] = ['k' => 'betrieb', 'titel' => 'Betrieb', 'stufe' => $stufe($z), 'zeilen' => $z, 'liste' => []];

    $alle = array_column($ab, 'stufe');
    return ['von' => gmdate('Y-m-d\TH:i:s\Z', $von), 'bis' => gmdate('Y-m-d\TH:i:s\Z', $bis), 'stufe' => in_array('bad', $alle, true) ? 'bad' : (in_array('warn', $alle, true) ? 'warn' : 'ok'),
            'abschnitte' => $ab];
}
/* Adresse der Sicherheitszentrale für Links in E-Mails (Modulregister; nie aus der Anfrage) */
function bereit_link(string $reiter = ''): string
{
    $a = (string)(MODULE['sicherheit']['oberflaechen']['intern']['adresse'] ?? '');
    return $a !== '' ? $a . ($reiter !== '' ? '#' . strtolower($reiter) : '') : '';
}
/* E-Mail im Stil der Benachrichtigungen: [Betreff, Text, HTML]. $abschnitte: [{titel, zeilen[[k, v, stufe?]], liste[], hinweis?}] */
function bereit_mail(string $titel, string $einleitung, array $abschnitte, string $reiter = ''): array
{
    global $CFG;
    $farbe = ['ok' => '#2e7d4f', 'warn' => '#b26a00', 'bad' => '#b3261e', 'info' => '#857c72'];
    $zeichen = ['ok' => '✓', 'warn' => '!', 'bad' => '✗', 'info' => '·'];
    $subject = '[' . $CFG['company'] . '] Sicherheit: ' . $titel;
    $t = "Hallo,\n\n" . $einleitung . "\n";
    $h = '<p style="margin:0 0 14px;">Hallo,</p><p style="margin:0 0 14px;">' . mail_h($einleitung) . '</p>';
    foreach ($abschnitte as $a) {
        $t .= "\n" . mb_strtoupper((string)$a['titel']) . "\n";
        $rows = '';
        foreach ((array)($a['zeilen'] ?? []) as $z) {
            $st = (string)($z[2] ?? 'info');
            $t .= '  ' . ($zeichen[$st] ?? '·') . ' ' . str_pad(mb_substr((string)$z[0], 0, 44) . ':', 46) . $z[1] . "\n";
            $rows .= '<tr><td style="padding:3px 8px 3px 0;color:' . ($farbe[$st] ?? '#857c72') . ';font-weight:bold;vertical-align:top;">' . ($zeichen[$st] ?? '·') . '</td>'
                . '<td style="padding:3px 12px 3px 0;color:#4a443e;vertical-align:top;">' . mail_h((string)$z[0]) . '</td><td style="padding:3px 0;font-weight:bold;">' . mail_h((string)$z[1]) . '</td></tr>';
        }
        $h .= '<p style="margin:18px 0 6px;font-weight:bold;">' . mail_h((string)$a['titel']) . '</p>'
            . ($rows !== '' ? '<table role="presentation" cellpadding="0" cellspacing="0" style="font-size:14px;">' . $rows . '</table>' : '');
        $liste = (array)($a['liste'] ?? []);
        if ($liste) {
            foreach ($liste as $x) $t .= '    – ' . $x . "\n";
            $h .= '<ul style="margin:6px 0 0;padding-left:20px;font-size:13px;color:#4a443e;">' . implode('', array_map(function ($x) { return '<li style="margin:2px 0;">' . mail_h((string)$x) . '</li>'; }, $liste)) . '</ul>';
        }
        if (($a['hinweis'] ?? '') !== '') { $t .= '  ' . $a['hinweis'] . "\n"; $h .= '<p style="margin:6px 0 0;font-size:12px;color:#857c72;">' . mail_h((string)$a['hinweis']) . '</p>'; }
    }
    $link = bereit_link($reiter);
    if ($link !== '') { $t .= "\nSicherheitszentrale: {$link}\n"; $h .= '<p style="margin:20px 0 0;">' . mail_button($link, 'Sicherheitszentrale öffnen') . '</p>'; }
    $foot = 'Automatisch erzeugt von der STAFL-Plattform (Modul Sicherheit). Empfänger: Verwaltung → E-Mail → Benachrichtigungen → Sicherheitsereignisse.';
    $t .= "\n" . $foot . "\n";
    return [$subject, $t, mail_layout($subject, $h, '', $foot)];
}
/* Bericht senden ($me = null: automatischer Versand). Ergebnis wird im Verlauf vermerkt. */
function bericht_senden(?array $me, bool $auto): array
{
    $to = notify_targets('sicherheit', true);
    if (!$me && !$to) { bericht_vermerken(['t' => now(), 'auto' => true, 'von' => '', 'an' => 0, 'ok' => 0, 'fehler' => 'keine Empfänger eingetragen']); return []; }
    if (!$to) fail('Keine Empfänger für Sicherheitsereignisse eingetragen (Verwaltung → E-Mail → Benachrichtigungen).', 422);
    if (!mail_cfg()) {
        if ($me) fail('Das Postfach für den E-Mail-Versand ist nicht eingerichtet.', 422);
        bericht_vermerken(['t' => now(), 'auto' => true, 'von' => '', 'an' => count($to), 'ok' => 0, 'fehler' => 'Postfach nicht eingerichtet']);
        return [];
    }
    $d = bericht_daten();
    $gesamt = ['ok' => 'alles in Ordnung', 'warn' => 'in Ordnung, mit Hinweisen', 'bad' => 'Handlungsbedarf'][$d['stufe']];
    $einl = 'hier ist der Sicherheitsbericht für ' . date('d.m.', strtotime($d['von'])) . ' bis ' . date('d.m.Y', strtotime($d['bis'])) . '. Gesamtbild: ' . $gesamt . '.'
        . ($auto ? '' : ' (Auf Wunsch von ' . $me['name'] . ' versendet.)');
    $inhalt = bereit_mail('Wochenbericht ' . date('d.m.Y', strtotime($d['bis'])) . ' – ' . $gesamt, $einl, $d['abschnitte'], 'Lage');
    $res = notify_send('sicherheit', $to, [], 0, false, $auto ? 'Wochenbericht' : (string)$me['name'], $inhalt);
    $ok = count(array_filter($res, function ($r) { return $r['ok']; }));
    $fehler = '';
    foreach ($res as $r) if (!$r['ok']) { $fehler = mb_substr((string)$r['error'], 0, 160); break; }
    $e = ['t' => now(), 'auto' => $auto, 'von' => $me ? (string)$me['name'] : '', 'an' => count($to), 'ok' => $ok, 'fehler' => $fehler, 'stufe' => $d['stufe']];
    bericht_vermerken($e);
    return $e;
}
function bericht_vermerken(array $e): void
{
    bereit_aendern(function (array &$d) use ($e) {
        $x = is_array($d['bericht'] ?? null) ? $d['bericht'] : [];
        $v = array_values(array_filter((array)($x['verlauf'] ?? []), 'is_array'));
        array_unshift($v, $e);
        $x['verlauf'] = array_slice($v, 0, BERICHT_VERLAUF_MAX);
        $d['bericht'] = $x;
    });
}
/* Automatischer Versand: von der Statusabfrage angemeldeter Mitarbeiter aufgerufen (api status). Liest nur das eigene Dokument;
   ist der Bericht fällig, wird die Woche unter Sperre vermerkt (genau ein Versand) und nach der Antwort versendet. */
function bericht_anstossen(): void
{
    try {
        $b = is_array(bereit_dok()['bericht'] ?? null) ? bereit_dok()['bericht'] : [];
        if (array_key_exists('an', $b) && empty($b['an'])) return;
        $woche = date('o-\WW');
        if (($b['woche'] ?? '') === $woche) return;
        $tag = (int)($b['tag'] ?? 1);
        if ((int)date('N') < ($tag >= 1 && $tag <= 7 ? $tag : 1) || (int)date('G') < BERICHT_AB_STUNDE) return;
        $los = bereit_aendern(function (array &$d) use ($woche) {
            $x = is_array($d['bericht'] ?? null) ? $d['bericht'] : [];
            if (($x['woche'] ?? '') === $woche) return false;
            $erst = empty($x['woche']);   // erster Aufruf überhaupt: nur die Woche vermerken, Versand ab der nächsten Woche
            $x['woche'] = $woche;
            $d['bericht'] = $x;
            return !$erst;
        });
        if (!$los) return;
        register_shutdown_function(function () {
            try {
                if (!empty($GLOBALS['store_tx'])) return;
                if (function_exists('fastcgi_finish_request')) fastcgi_finish_request();
                ignore_user_abort(true);
                @set_time_limit(60);
                bericht_senden(null, true);
            } catch (Throwable $e) {
                error_log('[wochenangebot] Wochenbericht: ' . $e->getMessage());
            }
        });
    } catch (Throwable $e) {
        error_log('[wochenangebot] Wochenbericht prüfen: ' . $e->getMessage());
    }
}
