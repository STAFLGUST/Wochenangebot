<?php
declare(strict_types=1);
/* Notfallmodus (Oberfläche: Modul Sicherheit; Dienst im Plattformkern, docs/plattform/modul-sicherheit.md).
   Ein Schalter für den Sicherheits-Notfall. Er wirkt ausschließlich über vorhandene Mechanismen – keine zweite Sperrlogik:
   - Kunden: wartung() (lib/sicherheit.php) meldet eine Wartung der Angebotsseite mit neutralem Hinweis → Kundenaktionen 503,
     Kundenseite und App zeigen die Wartung; angemeldete Mitarbeiter kommen nur noch als Administrator daran vorbei.
   - Mitarbeiter ohne Administratorrolle: jede sperrbare interne Oberfläche gilt als „in Wartung“ (modul_wartung_eintrag in
     lib/module.php) → Entscheidungstabelle regeln/wartung.toml: 503, Administratoren arbeiten weiter (GR-102/GR-107).
     Nicht sperrbar bleiben Dashboard, zentrale Anmeldung und das Modul Sicherheit.
   - Sitzungen: Kundensitzungen und Mitarbeitersitzungen ohne Administratorrolle werden beendet (optional auch die anderer
     Administratoren und die Sitzungen in der zentralen Anmeldung). Auf Keycloak-Hosts ist die Sperre die 503-Antwort.
   - E-Mail-Versand pausiert (mail_send_many in lib/kundenmail.php), außer Benachrichtigungen an die eingetragenen Empfänger.
   - Firewall: Vorlage „Notfall“ (fw_vorlage_anwenden); die vorherigen Einstellungen werden gesichert und beim Beenden
     wiederhergestellt (abwählbar).
   - Sofortige Benachrichtigung (ohne Bündelpause) und Protokoll (Vorgang „notfall“).
   Dokument „sicherheit-notfall“: {aktiv, seit, von, vonName, grund, kundentext, optionen, wirkung, vorher{sicherheit, firewall},
   bis, beendetVon, ende{…}, verlauf[…]}. Beenden: Administrator mit Bestätigung oder deploy/notfall-aus.sh auf dem Server. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const NOTFALL_DOK = 'sicherheit-notfall';
const NOTFALL_WORT = 'NOTFALL';
const NOTFALL_KUNDENTEXT = 'Unser Angebotsportal ist vorübergehend nicht erreichbar. Bitte versuchen Sie es später erneut.';
const NOTFALL_MITARBEITERTEXT = 'Wegen einer Sicherheitsmaßnahme sind die Anwendungen vorübergehend gesperrt. Bitte wenden Sie sich an einen Administrator.';
const NOTFALL_MAIL_TEXT = 'Versand pausiert: Der Notfallmodus ist aktiv.';
const NOTFALL_VERLAUF_MAX = 20;

/* Gespeicherter Zustand (je Anfrage einmal gelesen; nach Änderungen mit $neu = true) */
function notfall_dok(bool $neu = false): array
{
    static $d = null;
    if ($neu || $d === null) { $x = store_read(NOTFALL_DOK); $d = is_array($x) ? $x : []; }
    return $d;
}
function notfall(): ?array { $d = notfall_dok(); return !empty($d['aktiv']) ? $d : null; }
function notfall_aktiv(): bool { return notfall() !== null; }
function notfall_kundentext(array $n): string { $t = trim((string)($n['kundentext'] ?? '')); return $t !== '' ? $t : NOTFALL_KUNDENTEXT; }

/* Wartungseintrag einer Oberfläche im Notfall (für modul_wartung_eintrag): jede sperrbare interne Oberfläche */
function notfall_wartung(string $modul, string $oberflaeche): ?array
{
    $n = notfall();
    if (!$n) return null;
    $o = MODULE[$modul]['oberflaechen'][$oberflaeche] ?? null;
    if (!$o || $o['art'] !== 'intern' || empty($o['sperrbar'])) return null;
    return ['active' => true, 'message' => NOTFALL_MITARBEITERTEXT, 'until' => null, 'since' => $n['seit'] ?? null, 'by' => (string)($n['vonName'] ?? ''),
            'ab' => null, 'grund' => 'Notfallmodus: ' . (string)($n['grund'] ?? ''), 'notfall' => true];
}
/* Wer trotz Wartung der Angebotsseite die Kundenfunktionen nutzt: angemeldete Mitarbeiter (GR-009) – im Notfall nur Administratoren */
function kunden_wartung_ausnahme(?array $u): bool
{
    return $u !== null && (!notfall_aktiv() || ($u['role'] ?? '') === 'admin');
}
/* E-Mail-Versand gesperrt? (Benachrichtigungen setzen NOTFALL_MAIL_FREI, lib/benachrichtigung.php) */
function notfall_mail_gesperrt(): bool { return empty($GLOBALS['NOTFALL_MAIL_FREI']) && notfall_aktiv(); }

/* Anzeige für Status, Dashboard und Modul: alle sehen „aktiv seit“; Grund, Urheber und Wirkung nur Administratoren und
   Inhaber von sicherheit.sehen/sicherheit.notfall */
function notfall_anzeige(?array $u): ?array
{
    if (!$u) return null;
    $n = notfall();
    if (!$n) return null;
    $out = ['aktiv' => true, 'seit' => $n['seit'] ?? null];
    if (($u['role'] ?? '') === 'admin' || may($u, 'sicherheit.sehen') || may($u, 'sicherheit.notfall')) {
        $out += ['grund' => (string)($n['grund'] ?? ''), 'von' => (string)($n['vonName'] ?? ''), 'kundentext' => notfall_kundentext($n),
                 'optionen' => (array)($n['optionen'] ?? []), 'wirkung' => (array)($n['wirkung'] ?? []), 'firewallGesichert' => is_array($n['vorher'] ?? null)];
    }
    return $out;
}
/* Verlauf der letzten Notfälle (ohne Schnappschüsse) */
function notfall_verlauf(): array
{
    return array_values(array_filter((array)(notfall_dok()['verlauf'] ?? []), 'is_array'));
}

/* Wirkungen als Text (eine Quelle für Oberfläche und Benachrichtigung) und aktuelle Zahlen zur Vorschau */
function notfall_wirkungen(): array
{
    $sperrbar = [];
    foreach (MODULE as $id => $m) foreach ($m['oberflaechen'] as $oid => $o) {
        if ($o['art'] === 'intern' && $o['sperrbar'] && modul_freigabe($id, $oid) !== 'keine') $sperrbar[] = $o['name'] === $m['name'] ? $m['name'] : $m['name'] . ': ' . $o['name'];
    }
    $rollen = notfall_rollen();
    $sitz = 0; $admSitz = 0;
    foreach (sess_prune(store_read('sitzungen') ?? []) as $v) { if (($rollen[(string)($v['uid'] ?? '')] ?? '') === 'admin') $admSitz++; else $sitz++; }
    return [
        'punkte' => [
            ['kunden', 'Kunden sehen auf der Angebotsseite den Wartungshinweis; Anmeldung, Merkliste und Bestellwünsche pausieren.'],
            ['mitarbeiter', 'Mitarbeiter ohne Administratorrolle sind ausgesperrt (alle Anwendungen antworten mit „gesperrt“). Administratoren arbeiten weiter.'],
            ['sitzungen', 'Alle Kundensitzungen und die Sitzungen von Mitarbeitern ohne Administratorrolle werden beendet.'],
            ['mail', 'Der E-Mail-Versand pausiert (Rundmails, Angebote, Zugangsdaten, Bestellmails) – Benachrichtigungen an die eingetragenen Empfänger gehen weiter.'],
            ['firewall', 'Firewall auf „Notfall“: Sperre schon nach dem ersten Angriffsmuster für 7 Tage, Bedrohungsliste, Mitschnitt 60 Minuten. Die bisherigen Einstellungen werden gesichert.'],
            ['meldung', 'Sofortige Benachrichtigung an die Empfänger der Sicherheitsereignisse und Eintrag im Protokoll.'],
        ],
        'bereiche' => array_values(array_unique($sperrbar)),
        'zahlen' => ['mitarbeiterSitzungen' => $sitz, 'adminSitzungen' => $admSitz, 'kundenOnline' => count(array_unique(array_column(ksess_prune(store_read('kundensitzungen') ?? []), 'kid')))],
        'keycloak' => konten_eingerichtet(),
        'wort' => NOTFALL_WORT,
    ];
}
function notfall_rollen(): array
{
    $r = [];
    foreach (users_load() as $u) $r[(string)$u['id']] = (string)($u['role'] ?? '');
    return $r;
}

/* Auslösen. $b: grund (Pflicht), wort (= NOTFALL), kundentext, firewall (Standard an), admins (nur Administratoren:
   auch andere Administratorsitzungen beenden), keycloak (Sitzungen in der zentralen Anmeldung beenden). */
function notfall_ausloesen(array $me, array $b): array
{
    $grund = modul_text((string)($b['grund'] ?? ''), 300);
    if (mb_strlen($grund) < 5) fail('Bitte kurz den Grund angeben (mindestens 5 Zeichen).', 422);
    if (mb_strtoupper(trim((string)($b['wort'] ?? ''))) !== NOTFALL_WORT) fail('Zur Sicherheit bitte das Wort „' . NOTFALL_WORT . '“ eintippen.', 422);
    $kundentext = modul_text((string)($b['kundentext'] ?? ''), 500);
    $admin = ($me['role'] ?? '') === 'admin';
    $opt = ['firewall' => !array_key_exists('firewall', $b) || !empty($b['firewall']), 'admins' => $admin && !empty($b['admins']),
            'keycloak' => !empty($b['keycloak']) && konten_eingerichtet()];
    $jetzt = now();
    // Zustand setzen (unter Sperre: nur einmal gleichzeitig) – Schnappschuss der Einstellungen vor jeder Änderung
    with_lock(NOTFALL_DOK, function () use ($me, $grund, $kundentext, $opt, $jetzt) {
        $d = store_read(NOTFALL_DOK) ?? [];
        if (!empty($d['aktiv'])) fail('Der Notfallmodus ist bereits aktiv.', 409);
        $d = ['aktiv' => true, 'seit' => $jetzt, 'von' => (string)$me['username'], 'vonName' => (string)$me['name'], 'grund' => $grund,
              'kundentext' => $kundentext, 'optionen' => $opt, 'wirkung' => [],
              'vorher' => ['sicherheit' => store_read('sicherheit') ?? [], 'firewall' => store_read('firewall') ?? []],
              'verlauf' => (array)($d['verlauf'] ?? [])];
        store_write(NOTFALL_DOK, $d);
    });
    notfall_dok(true);
    $w = ['zeit' => $jetzt];
    // Firewall und Sicherheitseinstellungen: Vorlage „Notfall“ (wie Aktion fw_vorlage, ohne Abbruch wegen eigener Zwei-Faktor-Pflicht)
    if ($opt['firewall']) {
        try { $v = fw_vorlage_anwenden('notfall', $me, true); $w['firewall'] = 'Vorlage „Notfall“ angewendet' . $v['hinweis']; }
        catch (Throwable $e) { error_log('[wochenangebot] Notfall Firewall: ' . $e->getMessage()); $w['firewall'] = 'nicht angewendet: ' . mb_substr($e->getMessage(), 0, 160); }
    } else $w['firewall'] = 'unverändert (abgewählt)';
    // Sitzungen beenden: Kunden, Mitarbeiter ohne Administratorrolle (optional andere Administratoren) – nie die eigene
    $rollen = notfall_rollen();
    $mine = (string)($_SESSION['sid'] ?? '');
    $betroffen = [];
    $w['mitarbeiterSitzungen'] = sess_remove(function ($k, $v) use ($rollen, $mine, $opt, &$betroffen) {
        $uid = (string)($v['uid'] ?? '');
        if ($k === $mine || (($rollen[$uid] ?? '') === 'admin' && !$opt['admins'])) return false;
        $betroffen[$uid] = true;
        return true;
    });
    $w['kundenSitzungen'] = ksess_remove(function () { return true; });
    // Zentrale Anmeldung (Keycloak): Sitzungen der betroffenen Konten beenden (alle ohne Administratorrolle bzw. mit Option alle außer mir)
    if ($opt['keycloak']) {
        $ok = 0; $fehler = 0;
        foreach (users_load() as $u) {
            if (empty($u['active']) || (string)$u['id'] === (string)$me['id'] || (($u['role'] ?? '') === 'admin' && !$opt['admins'])) continue;
            try {
                [$k] = konten_finden($u);
                if (!$k || empty($k['id'])) continue;
                [$st] = konten_api('POST', 'users/' . rawurlencode((string)$k['id']) . '/logout');
                if ($st >= 200 && $st < 300) $ok++; else $fehler++;
            } catch (Throwable $e) { $fehler++; }
        }
        $w['keycloak'] = ['beendet' => $ok, 'fehler' => $fehler];
    }
    with_lock(NOTFALL_DOK, function () use ($w) {
        $d = store_read(NOTFALL_DOK) ?? [];
        if (empty($d['aktiv'])) return;
        $d['wirkung'] = $w;
        store_write(NOTFALL_DOK, $d);
    });
    notfall_dok(true);
    $facts = [['Ausgelöst von', $me['name'] . ' (' . $me['username'] . ')'], ['IP-Adresse', client_ip()], ['Grund', $grund],
              ['Firewall', $w['firewall']], ['Beendete Sitzungen', $w['mitarbeiterSitzungen'] . ' Mitarbeiter, ' . $w['kundenSitzungen'] . ' Kunden'],
              ['Wirkung', 'Kunden sehen Wartung, Mitarbeiter ohne Administratorrolle sind ausgesperrt, E-Mail-Versand pausiert']];
    if (isset($w['keycloak'])) $facts[] = ['Zentrale Anmeldung', $w['keycloak']['beendet'] . ' Konten abgemeldet' . ($w['keycloak']['fehler'] ? ', ' . $w['keycloak']['fehler'] . ' Fehler' : '')];
    audit('notfall', 'Notfallmodus ausgelöst: ' . $grund, [['k' => 'notfall', 'code' => '', 'name' => 'Notfallmodus', 'f' => 'Status', 'from' => 'aus', 'to' => 'aktiv']]);
    modul_verlauf_eintragen(['t' => $jetzt, 'wer' => (string)$me['name'], 'bereich' => 'alle', 'alt' => 'normal', 'neu' => 'wartung', 'grund' => 'Notfallmodus: ' . $grund, 'ab' => null, 'bis' => null]);
    notfall_benachrichtigen('NOTFALLMODUS AUSGELÖST', $facts);
    return notfall_anzeige($me) ?? [];
}

/* Beenden (Administrator). $b: firewall = true stellt die gesicherten Einstellungen wieder her (Standard), false behält die strengen. */
function notfall_beenden(array $me, array $b): array
{
    $zurueck = !array_key_exists('firewall', $b) || !empty($b['firewall']);
    $notiz = modul_text((string)($b['notiz'] ?? ''), 300);
    $r = notfall_ende((string)$me['name'], $zurueck, $notiz);
    if ($r === null) fail('Der Notfallmodus ist nicht aktiv.', 409);
    $GLOBALS['SEC'] = null; $GLOBALS['FWS'] = null;
    notfall_dok(true);
    audit('notfall', 'Notfallmodus beendet' . ($notiz !== '' ? ': ' . $notiz : ''), [['k' => 'notfall', 'code' => '', 'name' => 'Notfallmodus', 'f' => 'Status', 'from' => 'aktiv', 'to' => 'aus'],
        ['k' => 'notfall|fw', 'code' => '', 'name' => 'Notfallmodus', 'f' => 'Einstellungen', 'from' => '', 'to' => $r['einstellungen']]]);
    modul_verlauf_eintragen(['t' => now(), 'wer' => (string)$me['name'], 'bereich' => 'alle', 'alt' => 'wartung', 'neu' => 'normal', 'grund' => 'Notfallmodus beendet', 'ab' => null, 'bis' => null]);
    notfall_benachrichtigen('Notfallmodus beendet', [['Beendet von', $me['name'] . ' (' . $me['username'] . ')'], ['Dauer', $r['dauer']],
        ['Einstellungen', $r['einstellungen']], ['Notiz', $notiz !== '' ? $notiz : '–']]);
    return $r;
}
/* Gemeinsamer Abschluss (auch für das Server-Werkzeug deploy/notfall-aus.php, das denselben Ablauf ohne API nachbildet) */
function notfall_ende(string $wer, bool $einstellungenZurueck, string $notiz = ''): ?array
{
    return with_lock(NOTFALL_DOK, function () use ($wer, $einstellungenZurueck, $notiz) {
        $d = store_read(NOTFALL_DOK) ?? [];
        if (empty($d['aktiv'])) return null;
        $text = 'unverändert (streng)';
        if ($einstellungenZurueck && is_array($d['vorher'] ?? null) && !empty($d['optionen']['firewall'])) {
            store_write('sicherheit', (array)($d['vorher']['sicherheit'] ?? []));
            store_write('firewall', (array)($d['vorher']['firewall'] ?? []));
            $text = 'wie vor dem Notfall wiederhergestellt';
        } elseif (empty($d['optionen']['firewall'])) $text = 'nicht geändert (Firewall war abgewählt)';
        $ende = now();
        $s = max(0, strtotime($ende) - strtotime((string)($d['seit'] ?? $ende)));
        $dauer = $s >= 3600 ? intdiv($s, 3600) . ' Std. ' . intdiv($s % 3600, 60) . ' Min.' : max(1, intdiv($s, 60)) . ' Min.';
        $eintrag = ['seit' => $d['seit'] ?? null, 'bis' => $ende, 'von' => (string)($d['vonName'] ?? ''), 'beendetVon' => $wer, 'grund' => (string)($d['grund'] ?? ''),
                    'notiz' => $notiz, 'wirkung' => (array)($d['wirkung'] ?? []), 'einstellungen' => $text];
        $v = (array)($d['verlauf'] ?? []);
        array_unshift($v, $eintrag);
        store_write(NOTFALL_DOK, ['aktiv' => false, 'verlauf' => array_slice($v, 0, NOTFALL_VERLAUF_MAX), 'geaendert' => $ende]);
        return ['dauer' => $dauer, 'einstellungen' => $text, 'eintrag' => $eintrag];
    });
}

/* Sofortige Benachrichtigung nach der Antwort – ohne Bündelpause, auch wenn das Ereignis ausgeschaltet ist, solange Empfänger
   eingetragen sind (ein Notfall soll nie im Bündel untergehen) */
function notfall_benachrichtigen(string $titel, array $facts): void
{
    $item = ['ev' => 'sicherheit', 'title' => $titel, 'facts' => $facts, 't' => now()];
    register_shutdown_function(function () use ($item) {
        try {
            if (!empty($GLOBALS['store_tx'])) return;
            $to = notify_targets('sicherheit', true);
            if (!$to || !mail_cfg_intern()) return;
            if (function_exists('fastcgi_finish_request')) fastcgi_finish_request();
            notify_send('sicherheit', $to, [$item], 0, false, 'Notfallmodus');
        } catch (Throwable $e) {
            error_log('[wochenangebot] Notfall-Benachrichtigung: ' . $e->getMessage());
        }
    });
}
