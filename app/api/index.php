<?php
/*
 * Wochenangebot – API
 *
 * Öffentlich:
 *   GET  ?action=offer            veröffentlichtes Angebot
 * Eingabebereich (Anmeldung nötig, Schreibzugriffe zusätzlich mit CSRF-Token):
 *   Rollen: viewer (nur ansehen) < editor (bearbeiten/veröffentlichen) < admin (+ Nutzer, Protokoll)
 *   GET  ?action=status           Anmeldestatus / Ersteinrichtung nötig?
 *   POST ?action=setup            ersten Administrator anlegen (nur solange es keinen Nutzer gibt)
 *   POST ?action=login | logout   Anmeldung mit Benutzername + Passwort
 *   GET  ?action=draft            Entwurf + veröffentlichter Stand
 *   POST ?action=save_draft       Entwurf speichern
 *   POST ?action=discard_draft    Entwurf verwerfen
 *   POST ?action=publish          Entwurf veröffentlichen (vorheriger Stand wird archiviert)
 *   GET  ?action=versions         frühere Veröffentlichungen
 *   GET  ?action=version&id=…     eine frühere Veröffentlichung
 *   POST ?action=change_password
 *   GET  ?action=history_list | history_data   Preisverlauf (Wochen-Stände)
 *   GET  ?action=history_prev&week=&year=      Preise der Vorwoche (jüngste gespeicherte Woche davor)
 *   POST ?action=history_import | history_delete
 *   GET  ?action=stock            Bestand (Mengen, MHD) – nur angemeldet, nie öffentlich
 *   POST ?action=stock_import     Bestandsliste übernehmen (Bearbeiter)
 *   GET  ?action=einkauf          Fehlmengen offener Bestellwünsche gegenüber dem Bestand (angemeldet; Kundennamen ab Bearbeiter)
 *   POST ?action=einkauf_melden   Einkauf per E-Mail benachrichtigen (Bearbeiter; Empfänger unter Benachrichtigungen)
 *   GET  ?action=master           Stammdaten je Artikelnummer (Bezeichnung, Fleischart, Herkunft, Zustand)
 *   POST ?action=master_save      Stammdaten speichern (Bearbeiter)
 *   GET  ?action=users | log      Nutzerliste / Protokoll (nur Administrator)
 *   GET  ?action=security_status  Sicherheitsübersicht (nur Administrator)
 *   POST ?action=security_diag | security_export   nur lesende Diagnosen; Sicherheitsprotokoll als CSV (Administrator)
 *   GET  ?action=security_integrity  letzte Dateiprüfung; POST {run:true} jetzt prüfen (Administrator)
 *   POST ?action=security_save | session_end | ip_unblock | user_unlock | geo_update
 *   GET  ?action=offers            Angebote (Standard + Kundenangebote), angemeldet
 *   POST ?action=offers_save       Angebote anlegen/umbenennen/Regel ändern (Bearbeiter), löschen (Administrator)
 *   GET  ?action=kunden            Kundenstammdaten (nur Administrator); POST kunde_save | kunde_delete
 *   POST ?action=kunden_import     Kundenstammdaten aus der Warenwirtschaft (CSV im Browser gelesen; pruefen = Vorschau)
 *   GET  ?action=import_arten · POST import_pruefen | import_uebernehmen   Importzentrale (Recht je Importart)
 *   GET  ?action=einzel_liste | einzel_detail | einzel_artikel   Einzelangebote je Kunde; POST einzel_save | einzel_status | einzel_loeschen | einzel_senden
 *   GET  ?action=kundengruppen     Kundengruppen (Stammdaten); POST kundengruppen_save (ganze Liste, Revision)
 *   GET  ?action=vkgruppen         VK-Gruppen (Stammdaten, Artikel über vkGruppe); POST vkgruppen_save
 *   GET  ?action=vertreter         Vertreter (Stammdaten, Kunden über vertreter/vertreter2); POST vertreter_save
 *   GET  ?action=app_info          Grunddaten für die App (Mindestversion, Bestellfunktion, Wartung); docs/app-api.md
 *   GET  ?action=kunde_status      Kunden-Anmeldung auf der Angebotsseite; POST kunde_login | kunde_logout | kunde_passwort
 *   POST ?action=kunde_token_check | kunde_token_set   Passwort über Link aus der E-Mail festlegen (Einladung/Zurücksetzen)
 *   GET  ?action=fw_status | fw_verkehr | fw_export   Schutzzentrale (Administrator); POST fw_save | fw_sperren | fw_freigeben | fw_feed_update | fw_vorlage | fw_import
 *   GET  ?action=waf_probe&p=…     Falle für Angriffswerkzeuge (Caddy leitet z. B. /wp-login.php hierher) → 404, Treffer zählen
 *   GET  ?action=mail_info         Kurzinfo E-Mail-Versand (eingerichtet, Angebotswoche) für Nutzer mit Kundenrechten
 *   GET  ?action=mail_status       E-Mail-Versand (nur Administrator); POST mail_save | mail_test | kunde_mail | kunden_rundmail | kunden_mail_vorschau
 *   POST ?action=kunde_bestellung  Bestellwunsch eines Kunden (Preise serverseitig aus dem Angebot) → E-Mail an uns (+ Kopie)
 *   POST ?action=bestell_settings_save   Bestellfunktion ein/aus, Kopie an Kunden (nur Administrator)
 *   POST ?action=fracht_save             Frachtfreigrenze, Frachtanteil je Staffel, Zusatz im Hinweis (nur Administrator)
 *   POST ?action=benachrichtigung_save | benachrichtigung_test   Benachrichtigungen an Mitarbeiter (nur Administrator)
 *   POST ?action=wartung_save      Wartungsmodus ein/aus (Administrator, mit Passwortbestätigung)
 *   GET  ?action=kunde_merkliste   Merkliste des angemeldeten Kunden; POST kunde_merkliste_save (Kunden-CSRF)
 *   POST ?action=kunde_abmelden_info | kunde_abmelden   Abmeldelink aus der Angebotsmail (öffentlich, Code im Link)
 *   POST ?action=abmelden1&t=…     Ein-Klick-Abmeldung aus dem E-Mail-Programm (RFC 8058, Formular statt JSON)
 *   POST ?action=mail_konto_save   Postfach/Absender speichern (nur Administrator; Passwort verschlüsselt, nie zurückgegeben)
 *   POST ?action=login_2fa        zweiter Anmeldeschritt (Code aus der Authenticator-App)
 *   POST ?action=twofa_begin | twofa_enable | twofa_disable   eigene Zwei-Faktor-Anmeldung
 *   GET  ?action=passkey_list · POST passkey_begin | passkey_register | passkey_rename | passkey_delete   eigene Passkeys
 *   POST ?action=passkey_login_begin | passkey_login   Anmeldung mit Passkey (ohne Benutzername oder als zweiter Schritt)
 *   POST ?action=user_save | user_delete   (inkl. abweichender Rechte je Nutzer: grant/deny)
 *   GET  ?action=rechte · POST ?action=rechte_save   Rechte je Rolle (Administrator)
 *   GET  ?action=module_status   Module, Oberflächen, Freigabe, Wartung und Zugang (angemeldet; lib/module.php)
 *   POST ?action=modul_wartung_save   Wartung eines Bereichs starten/planen/beenden (Administrator, immer mit Bestätigung)
 *   HR (Oberfläche hr.intern): GET hr_start | hr_monat · POST hr_antrag | hr_antrag_zurueckziehen   eigener Urlaub (hr.antrag)
 *   GET hr_verwaltung · POST hr_entscheiden | hr_eintrag_save | hr_person_save | hr_einstellungen_save | hr_export | hr_import_*   Personalstelle (hr.verwalten)
 *
 * Alle Daten liegen als .php-Dateien mit Zugriffssperre im Datenordner –
 * sie lassen sich auch ohne .htaccess nicht direkt im Browser abrufen.
 */
declare(strict_types=1);
const WA_API = true;
// Fehler nie im Browser anzeigen (nur ins Server-Protokoll) und die PHP-Version nicht verraten –
// unabhängig von der php.ini des Containers (das offizielle Image zeigt Fehler sonst an)
ini_set('display_errors', '0');
ini_set('display_startup_errors', '0');
ini_set('log_errors', '1');
header_remove('X-Powered-By');
// Datum und Uhrzeit (E-Mails, Ausdrucke, „gültig bis“, Wunschtermine) in deutscher Zeit – das PHP-Image rechnet sonst in UTC
// und zeigt nachts bzw. in Mails 1–2 Stunden falsch an. Gespeichert wird weiter in UTC (now(), gmdate).
date_default_timezone_set('Europe/Berlin');

$CFG = require __DIR__ . '/config.php';
require __DIR__ . '/geo.php';
require __DIR__ . '/ort.php';
require __DIR__ . '/mail.php';
$DATA = rtrim((string)$CFG['data_dir'], '/');
require __DIR__ . '/storage.php';
require __DIR__ . '/orders.php';
require __DIR__ . '/order_outbox.php';
const CATEGORIES = ['Rind', 'Kalb', 'Schwein', 'Lamm & Schaf', 'Geflügel', 'Knochen', 'Sonstiges'];
const CONDITIONS = ['frisch', 'gefroren', 'frisch-gefroren', 'dry-aged', 'unbekannt'];
const PRICE_STATUS = ['value', 'request', 'none'];

if (!function_exists('mb_substr')) { function mb_substr($s, $start, $len = null) { return $len === null ? substr($s, $start) : substr($s, $start, $len); } }
if (!function_exists('mb_strlen')) { function mb_strlen($s) { return strlen(utf8_decode($s)); } }

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');

set_exception_handler(function (Throwable $e) {
    store_rollback();
    error_log('[wochenangebot] ' . $e->getMessage());
    respond(['ok' => false, 'error' => 'Interner Fehler auf dem Server.'], 500);
});

/* Funktionen nach Fachbereichen (app/api/lib) */
require __DIR__ . '/lib/kern.php';
require __DIR__ . '/lib/nutzer.php';
require __DIR__ . '/lib/rechte.php';
require __DIR__ . '/lib/sicherheit.php';
require __DIR__ . '/lib/sitzung.php';
require __DIR__ . '/lib/oidc.php';
require __DIR__ . '/lib/passkey.php';
require __DIR__ . '/lib/protokoll.php';
require __DIR__ . '/lib/angebote.php';
require __DIR__ . '/lib/kunden.php';
require __DIR__ . '/lib/kundenmail.php';
require __DIR__ . '/lib/fracht.php';
require __DIR__ . '/lib/einzelangebote.php';
require __DIR__ . '/lib/benachrichtigung.php';
require __DIR__ . '/lib/einkauf.php';
require __DIR__ . '/lib/diagnose.php';
require __DIR__ . '/lib/auswertung.php';
require __DIR__ . '/lib/preisverlauf.php';
require __DIR__ . '/lib/bestand.php';
require __DIR__ . '/lib/firewall.php';
require __DIR__ . '/lib/integritaet.php';
require __DIR__ . '/lib/geraete.php';
require __DIR__ . '/lib/aktionen-liste.php';   // Aktionsregister (erzeugt aus regeln/aktionen/*.toml)
require __DIR__ . '/lib/module-liste.php';     // Modulregister und Entscheidungstabelle (erzeugt aus regeln/)
require __DIR__ . '/lib/module.php';
require __DIR__ . '/lib/herkunft.php';
/* Importverträge der Daten-Eigentümer und Importzentrale (docs/plattform/schnittstellen/import.md) */
require __DIR__ . '/module/verwaltung/import.php';
require __DIR__ . '/module/bestand/import.php';
require __DIR__ . '/module/angebot/import.php';
require __DIR__ . '/module/verwaltung/importzentrale.php';
/* Fachmodule mit eigener Oberfläche */
require __DIR__ . '/module/hr/urlaub.php';
require __DIR__ . '/module/hr/export.php';
require __DIR__ . '/module/hr/import.php';

/* ---------------- Aktionen ---------------- */

$action = (string)($_GET['action'] ?? '');
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
/* Eigenschaften der Aktion aus dem Register (regeln/aktionen/<modul>.toml → lib/aktionen-liste.php): Modul, Oberfläche,
   schreibend, öffentlich, pausiert im Wartungsmodus. Unbekannte Aktionen: nicht öffentlich, nicht schreibend → am Ende 404.
   Neue Aktionen nur dort eintragen und `python3 werkzeuge/regeln.py erzeugen` ausführen (die CI prüft das). */
$AKTION = AKTIONEN[$action] ?? null;
/* Nur Anfragen von der eigenen Seite (lib/herkunft.php, GR-109) – vor allen weiteren Prüfungen, Firewall und Anmeldung */
herkunft_pruefen($AKTION, $method);
/* Aktion nur auf ihrem Host (lib/herkunft.php, GR-109): Aktionen eigener Modulseiten (z. B. hr.intern) nur dort */
host_pruefen($AKTION);
$schreibend = $AKTION !== null && ($AKTION['schreibend'] === true || ($AKTION['schreibend'] === 'post' && $method === 'POST'));
if ($schreibend) {
    if ($method !== 'POST') fail('Methode nicht erlaubt.', 405);
    if (stripos((string)($_SERVER['CONTENT_TYPE'] ?? ''), 'application/json') !== 0) fail('Ungültige Anfrage.', 415);
}

/* Keycloak-Host (lib/oidc.php): eigene Anmeldeverfahren gibt es dort nicht (GR-110) – nur zentrale Anmeldung */
if ($AKTION !== null && $AKTION['lokale_anmeldung'] && oidc_modus()) fail('Die Anmeldung erfolgt zentral über die STAFL-Anmeldung.', 403);

/* Schutz: Sperrliste, Firewall (Angriffsmuster), Fehlerbremse und Live-Verkehr (lib/firewall.php) */
fw_guard($action);

/* Ländersperre (ganze Seite oder nur Eingabebereich) */
/* Öffentlicher Bereich = Angebotsseite inkl. Kunden-Anmeldung (Kundenangebote verlangen dort selbst eine Anmeldung) */
$isPublic = $AKTION !== null && $AKTION['oeffentlich'] && !($action === 'offer' && !empty($_GET['draft']));
// Mitarbeiter-Sitzung ruft ein nicht öffentliches Angebot ab (Kundenpreise, Einzelangebote): gelten IP-Freigabe und
// Ländersperre des Eingabebereichs – auch wenn die Aktion sonst zur öffentlichen Angebotsseite gehört
if ($isPublic && $action === 'offer') {
    $oidQ = (string)($_GET['angebot'] ?? OFFER_STD);
    if (($oidQ !== '' && $oidQ !== OFFER_STD) || !std_public()) { if (current_user()) $isPublic = false; }
}
$S = sec();
if (!empty($S['geoEnabled']) && (!$isPublic || $S['geoScope'] === 'all')) {
    $cc = geo_blocked(client_ip(), $S);
    if ($cc !== null) {
        geo_count($cc);
        fail('Der Zugriff aus Ihrem Land ist leider nicht möglich.', 403);
    }
}

/* Wartungsmodus: Angebotsseite und Kundenfunktionen pausieren; Mitarbeiter arbeiten normal weiter.
   Abmelden vom Wochenangebot und Kunden-Abmelden bleiben immer möglich. */
if ($AKTION !== null && $AKTION['kunden_wartung'] && ($W = wartung()) && !current_user()) {
    header('Retry-After: 600');
    respond(['ok' => false, 'wartung' => true, 'error' => $W['message'], 'until' => $W['until']], 503);
}

/* IP-Freigabe für den Eingabebereich (die öffentliche Angebotsseite bleibt frei) */
if (!$isPublic) {
    if (!empty($S['ipEnabled']) && $S['adminIps'] && !ip_allowed(client_ip(), $S['adminIps'])) {
        fail('Der Eingabebereich ist von dieser Internetadresse (' . client_ip() . ') aus nicht freigegeben.', 403);
    }
}

/* Wartung und Freigabe je Oberfläche (lib/module.php, GR-102/GR-107) – nach Länder- und IP-Sperre, vor der Aktion */
modul_durchsetzen($AKTION);

try {
    orders_action($action);
    // Aktionen nach Fachbereichen (app/api/aktionen); keine passende Aktion → 404
    require __DIR__ . '/aktionen/angebote.php';
    require __DIR__ . '/aktionen/kundenportal.php';
    require __DIR__ . '/aktionen/mail.php';
    require __DIR__ . '/aktionen/kundenverwaltung.php';
    require __DIR__ . '/aktionen/zugang.php';
    require __DIR__ . '/aktionen/passkey.php';
    require __DIR__ . '/aktionen/bestand.php';
    require __DIR__ . '/aktionen/einkauf.php';
    require __DIR__ . '/aktionen/verwaltung.php';
    require __DIR__ . '/aktionen/entwurf.php';
    require __DIR__ . '/aktionen/preisverlauf.php';
    require __DIR__ . '/aktionen/auswertung.php';
    require __DIR__ . '/aktionen/app.php';
    require __DIR__ . '/aktionen/kundengruppen.php';
    require __DIR__ . '/aktionen/einzelangebote.php';
    require __DIR__ . '/aktionen/schutz.php';
    require __DIR__ . '/aktionen/integritaet.php';
    require __DIR__ . '/aktionen/module.php';
    require __DIR__ . '/aktionen/importzentrale.php';
    require __DIR__ . '/aktionen/hr.php';
    fail('Unbekannte Aktion.', 404);
} catch (InvalidArgumentException $e) {
    store_rollback();
    fail($e->getMessage(), 422);
}
