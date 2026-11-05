<?php
declare(strict_types=1);
/* Postausgang von innen (ADR-007, Zielarchitektur Kundenseite Regel 4): Die Kundenseite (Container „app“, WA_POSTAUSGANG=
   warteschlange) verschickt keine E-Mails und kennt kein Postfach-Passwort. Sie legt Versandaufträge im Dokument „postausgang“
   ab; der Dienst „postausgang“ (api/postausgang.php, gleiches Image, Zugangsdaten nur dort und in app-mitarbeiter) verschickt
   sie und meldet sich im Dokument „postausgang-stand“. Ohne WA_POSTAUSGANG versendet jede Anfrage wie bisher selbst.
   Aufträge: bestellung (Bestellwunsch: Versandaufträge stehen beim Vorgang, order_outbox.php), benachrichtigung (Ereignisse an
   Mitarbeiter, lib/benachrichtigung.php), hinweis (Ab-/Wiederanmeldung vom Wochenangebot, lib/kundenmail.php). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php bzw. api/postausgang.php nutzbar

const POSTAUSGANG_MAX = 500;                     // offene Aufträge höchstens (Überlauf: älteste Benachrichtigungen fallen weg)
const POSTAUSGANG_WIEDERHOLEN = [60, 300, 1800];   // Bestellwunsch nicht zugestellt: neue Versuche nach 1, 5 und 30 Minuten
const POSTAUSGANG_BEREIT = 900;                  // ohne Lebenszeichen des Dienstes seit 15 Minuten nimmt das Portal keine Bestellwünsche an
const POSTAUSGANG_DURCHSICHT = 600;              // alle 10 Minuten alle Vorgänge auf liegengebliebene Versandaufträge prüfen
/* Automatisch wiederholt wird nur, was nachweislich nicht beim Mailserver angekommen ist (Fehler vor der Übertragung der Nachricht
   oder ausdrückliche Ablehnung, app/api/mail.php). Unklare Fälle – z. B. Verbindung nach dem Senden abgebrochen – bleiben wie bisher
   für das bestätigte Nachsenden im Eingabebereich stehen (docs/bestell-mailversand.md: kein unbeaufsichtigter Doppelversand). */
const POSTAUSGANG_SICHER_NICHT_ZUGESTELLT = '/^(Keine Verbindung zum Mailserver|Mailserver nicht bereit|Begrüßung|Der Mailserver bietet keine Verschlüsselung|Verschlüsselung –|Verschlüsselte Verbindung zum Mailserver fehlgeschlagen|Anmeldung am Mailserver|Unverschlüsselter Versand ist nur|Das gespeicherte Postfach-Passwort kann nicht entschlüsselt|Absender abgelehnt|Empfänger abgelehnt|Versand abgelehnt|Nachricht abgelehnt|E-Mail-Versand ist nicht eingerichtet|Versand pausiert)/u';
function postausgang_wiederholbar(array $j): bool
{
    return ($j['state'] ?? '') === 'failed' && preg_match(POSTAUSGANG_SICHER_NICHT_ZUGESTELLT, (string)($j['error'] ?? '')) === 1;
}

/* Kundenseite: Aufträge nur ablegen, nie selbst senden */
function postausgang_warteschlange(): bool { return env_str('WA_POSTAUSGANG') === 'warteschlange'; }

/* Auftrag ablegen. $daten wird unverändert an den Dienst übergeben (keine Geheimnisse, keine Postfachdaten). */
function postausgang_ablegen(string $art, array $daten): void
{
    with_lock('postausgang', function () use ($art, $daten) {
        $liste = postausgang_liste();
        $liste[] = ['id' => bin2hex(random_bytes(8)), 'art' => $art, 't' => now(), 'faellig' => time(), 'versuche' => 0] + $daten;
        store_write('postausgang', ['auftraege' => postausgang_kuerzen($liste)]);
    });
}
function postausgang_liste(): array
{
    $d = store_read('postausgang');
    return is_array($d['auftraege'] ?? null) ? array_values(array_filter($d['auftraege'], 'is_array')) : [];
}
/* Überlauf: zuerst die ältesten Benachrichtigungen und Hinweise verwerfen – Bestellwünsche stehen ohnehin beim Vorgang und
   werden bei der Durchsicht gefunden */
function postausgang_kuerzen(array $liste): array
{
    while (count($liste) > POSTAUSGANG_MAX) {
        $i = null;
        foreach ($liste as $k => $a) if (($a['art'] ?? '') !== 'bestellung') { $i = $k; break; }
        unset($liste[$i ?? array_key_first($liste)]);
    }
    return array_values($liste);
}

/* Stand des Dienstes: Lebenszeichen und ob ein Postfach eingerichtet ist (die Kundenseite kann das selbst nicht prüfen) */
function postausgang_stand(): array
{
    $d = store_read('postausgang-stand');
    return is_array($d) ? $d : [];
}
function postausgang_versand_bereit(): bool
{
    $s = postausgang_stand();
    return !empty($s['versand']) && (int)($s['t'] ?? 0) > time() - POSTAUSGANG_BEREIT;
}

/* Ein Durchgang des Dienstes: fällige Aufträge abarbeiten, gelegentlich alle Vorgänge prüfen, Lebenszeichen schreiben.
   Ergebnis: Anzahl erledigter, erneut eingeplanter und fehlgeschlagener Aufträge. */
function postausgang_lauf(?int $jetzt = null): array
{
    $jetzt ??= time();
    $r = ['erledigt' => 0, 'wieder' => 0, 'fehler' => 0];
    // fällige Aufträge übernehmen (aus der Liste nehmen; erneute Versuche werden neu abgelegt)
    $faellig = with_lock('postausgang', function () use ($jetzt) {
        $liste = postausgang_liste(); $jetztDran = []; $rest = [];
        foreach ($liste as $a) { if ((int)($a['faellig'] ?? 0) <= $jetzt) $jetztDran[] = $a; else $rest[] = $a; }
        if ($jetztDran) store_write('postausgang', ['auftraege' => $rest]);
        return $jetztDran;
    });
    foreach ($faellig as $a) {
        try {
            $nochmal = postausgang_ausfuehren($a);
            if ($nochmal === null) { $r['erledigt']++; continue; }
            if ($nochmal === false) { $r['fehler']++; continue; }
            postausgang_wieder($a, $nochmal); $r['wieder']++;
        } catch (Throwable $e) {
            store_rollback();
            $r['fehler']++;
            error_log('[postausgang] ' . ($a['art'] ?? '?') . ': ' . $e->getMessage());
        }
    }
    // Durchsicht: Vorgänge mit offenen Versandaufträgen ohne Auftrag in der Liste (z. B. Abbruch zwischen Speichern und Ablegen)
    $stand = postausgang_stand();
    if ((int)($stand['durchsicht'] ?? 0) <= $jetzt - POSTAUSGANG_DURCHSICHT) {
        $offen = array_column(array_filter(postausgang_liste(), fn($a) => ($a['art'] ?? '') === 'bestellung'), 'nr');
        foreach (store_read('bestellungen') ?? [] as $o) {
            if (!is_array($o) || in_array($o['nr'] ?? '', $offen, true)) continue;
            if (!array_filter($o['outbox'] ?? [], fn($j) => ($j['state'] ?? '') === 'queued')) continue;
            try { order_outbox_send((string)$o['nr'], null, null, 'Postausgang'); $r['erledigt']++; }
            catch (Throwable $e) { store_rollback(); $r['fehler']++; error_log('[postausgang] Durchsicht ' . $o['nr'] . ': ' . $e->getMessage()); }
        }
        $stand['durchsicht'] = $jetzt;
    }
    // Kopien veröffentlichter Dokumente (ab Trennstufe 3, ADR-007 Stufe 2c): eine fremde Änderung im gemeinsamen Ordner wird aus dem
    // internen Stand wiederhergestellt und als Sicherheitsereignis gemeldet
    try {
        $fremd = array_keys(array_filter(store_kopien_abgleichen()));
        if ($fremd) {
            error_log('[postausgang] Veröffentlichte Daten im gemeinsamen Ordner verändert, wiederhergestellt: ' . implode(', ', $fremd));
            audit('security', 'Veröffentlichte Daten im gemeinsamen Ordner verändert – aus dem internen Stand wiederhergestellt: ' . implode(', ', $fremd), [],
                  ['username' => 'postausgang', 'name' => 'Postausgang', 'role' => 'system']);
        }
    } catch (Throwable $e) { store_rollback(); error_log('[postausgang] Abgleich der Kopien: ' . $e->getMessage()); }
    // Auszug aus Bestand und Stammdaten für die Kundenseite (ab Trennstufe 2): bei jedem Durchgang nach Zeitstempel, bei der
    // Durchsicht vollständig – falls eine Änderung den Auszug nicht neu geschrieben hat (z. B. Abbruch dazwischen)
    try { artikelauszug_aktualisieren(isset($stand['durchsicht']) && $stand['durchsicht'] === $jetzt); }
    catch (Throwable $e) { store_rollback(); error_log('[postausgang] Artikelauszug: ' . $e->getMessage()); }
    // Lebenszeichen (höchstens einmal je Minute schreiben) und ob überhaupt ein Postfach eingerichtet ist
    $versand = mail_cfg() !== null;
    if ((int)($stand['t'] ?? 0) <= $jetzt - 60 || ($stand['versand'] ?? null) !== $versand || isset($stand['durchsicht']) && $stand['durchsicht'] === $jetzt) {
        $stand['t'] = $jetzt; $stand['versand'] = $versand; $stand['intern'] = mail_account('intern') !== null;
        with_lock('postausgang-stand', function () use ($stand) { store_write('postausgang-stand', $stand); });
    }
    return $r;
}
/* Einen Auftrag ausführen. Rückgabe: null = erledigt, false = endgültig fehlgeschlagen, int = erneut versuchen in Sekunden.
   Aufträge stammen von der Kundenseite und gelten als unzuverlässig (ADR-007 Stufe 2b): Empfänger und Kundendaten kommen nie aus
   dem Auftrag, sondern aus den internen Einstellungen und Stammdaten; Benachrichtigungen nur der Art, die die Kundenseite auslöst. */
const POSTAUSGANG_HINWEIS_TAG = 10;   // Abmeldehinweise je Kunde und Tag höchstens
function postausgang_ausfuehren(array $a)
{
    switch ($a['art'] ?? '') {
        case 'bestellung': return postausgang_bestellung((string)($a['nr'] ?? ''), (int)($a['versuche'] ?? 0));
        case 'benachrichtigung': notify_verarbeiten(postausgang_ereignisse($a['items'] ?? null)); return null;
        case 'hinweis': postausgang_hinweis($a); return null;
    }
    error_log('[postausgang] unbekannter Auftrag: ' . ($a['art'] ?? '?'));
    return false;
}
/* Ereignisse der Kundenseite: nur Sicherheitsereignisse (Anmeldesperre, Datenleck …), Texte gekürzt – Empfänger bestimmen die
   internen Einstellungen (notify_targets) */
function postausgang_ereignisse($items): array
{
    $out = [];
    foreach (is_array($items) ? array_slice($items, 0, 20) : [] as $it) {
        if (!is_array($it) || ($it['ev'] ?? '') !== 'sicherheit' || !is_string($it['title'] ?? null)) continue;
        $facts = [];
        foreach (is_array($it['facts'] ?? null) ? array_slice($it['facts'], 0, 12) : [] as $f) {
            if (is_array($f) && is_scalar($f[0] ?? null) && is_scalar($f[1] ?? null)) $facts[] = [mb_substr((string)$f[0], 0, 60), mb_substr((string)$f[1], 0, 300)];
        }
        $t = is_string($it['t'] ?? null) && strtotime($it['t']) ? $it['t'] : now();
        $out[] = ['ev' => 'sicherheit', 'title' => mb_substr($it['title'], 0, 200), 'facts' => $facts, 't' => $t];
    }
    return $out;
}
/* Abmeldehinweis: Kunde aus den internen Stammdaten (nur die Kennung kommt aus dem Auftrag); nur wenn die Änderung dort auch
   gespeichert ist, höchstens POSTAUSGANG_HINWEIS_TAG je Kunde und Tag */
function postausgang_hinweis(array $a): void
{
    $kid = is_array($a['kunde'] ?? null) ? (string)($a['kunde']['id'] ?? '') : '';
    $ab = !empty($a['ab']);
    $c = null;
    foreach (customers_load()['customers'] as $x) if (($x['id'] ?? '') === $kid) $c = $x;
    if ($c === null) { error_log('[postausgang] Abmeldehinweis: Kunde unbekannt'); return; }
    $angemeldet = !array_key_exists('mailAngebot', $c) || !empty($c['mailAngebot']);
    if ($angemeldet === $ab) { error_log('[postausgang] Abmeldehinweis: Stand des Kunden ' . $kid . ' passt nicht – verworfen'); return; }
    $seit = gmdate('Y-m-d\TH:i:s', time() - 86400); $n = 0;
    foreach (store_read('mailversand') ?? [] as $e) if (($e['typ'] ?? '') === 'hinweis' && ($e['kid'] ?? '') === $kid && (string)($e['t'] ?? '') >= $seit) $n++;
    if ($n >= POSTAUSGANG_HINWEIS_TAG) { error_log('[postausgang] Abmeldehinweis: Tagesgrenze für Kunde ' . $kid); return; }
    $t = is_string($a['t'] ?? null) && strtotime($a['t']) ? $a['t'] : now();
    abmelde_hinweis_senden($c, $ab, $t);
}
/* Bestellwunsch: offene Versandaufträge senden; sicher nicht zugestellte nach POSTAUSGANG_WIEDERHOLEN erneut versuchen.
   Danach (oder bei unklarem Ausgang sofort) bleibt der Vorgang mit „E-Mail offen“ in den Bestellwünschen stehen – dort kann
   das Team nach Prüfung erneut senden. */
function postausgang_bestellung(string $nr, int $versuche)
{
    try {
        $o = order_outbox_send($nr, null, null, 'Postausgang');
        // erneute Versuche: zuerst an das Team, dann die Kopie an den Kunden (die verlangt eine zugestellte Mail an das Team)
        if ($versuche > 0) {
            $jobs = $o['outbox'] ?? [];
            usort($jobs, fn($x, $y) => ($x['kind'] === 'bestellung' ? 0 : 1) <=> ($y['kind'] === 'bestellung' ? 0 : 1));
            foreach ($jobs as $j) if (postausgang_wiederholbar($j)) {
                try { $o = order_outbox_send($nr, (string)$j['id'], (int)$j['attempts'], 'Postausgang'); }
                catch (WaAntwort $e) { if ($e->status !== 409) throw $e; }   // inzwischen geändert oder Team noch ohne Mail
            }
            $o = order_outbox_send($nr, null, null, 'Postausgang');   // Kopie an den Kunden, sobald das Team die Mail hat
        }
    } catch (WaAntwort $e) {
        if ($e->status === 404) return false;                                 // Vorgang gelöscht
        if ($e->status === 409) return 30;                                    // Versand läuft gerade (z. B. im Eingabebereich)
        throw $e;
    }
    $offen = array_filter($o['outbox'] ?? [], 'postausgang_wiederholbar');
    if (!$offen) return null;
    return POSTAUSGANG_WIEDERHOLEN[$versuche] ?? false;
}
function postausgang_wieder(array $a, int $sekunden): void
{
    $a['versuche'] = (int)($a['versuche'] ?? 0) + 1;
    $a['faellig'] = time() + $sekunden;
    with_lock('postausgang', function () use ($a) {
        $liste = postausgang_liste();
        $liste[] = $a;
        store_write('postausgang', ['auftraege' => postausgang_kuerzen($liste)]);
    });
}
