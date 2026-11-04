<?php
declare(strict_types=1);
/* Grundlagen laden: Einstellungen, Speicherschicht und alle Funktionen der Fachbereiche – gemeinsam für den API-Einstieg
   (api/index.php) und den Dienst „postausgang“ (api/postausgang.php, ADR-007). Setzt $CFG und $DATA im globalen
   Gültigkeitsbereich; nur einbinden, nicht direkt aufrufen. Neue Funktionsdateien hier eintragen, Aktionen in api/index.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php bzw. api/postausgang.php nutzbar

$CFG = require dirname(__DIR__) . '/config.php';
require dirname(__DIR__) . '/geo.php';
require dirname(__DIR__) . '/ort.php';
require dirname(__DIR__) . '/mail.php';
$DATA = rtrim((string)$CFG['data_dir'], '/');
require dirname(__DIR__) . '/storage.php';
require dirname(__DIR__) . '/orders.php';
require dirname(__DIR__) . '/order_outbox.php';
const CATEGORIES = ['Rind', 'Kalb', 'Schwein', 'Lamm & Schaf', 'Geflügel', 'Knochen', 'Sonstiges'];
const CONDITIONS = ['frisch', 'gefroren', 'frisch-gefroren', 'dry-aged', 'unbekannt'];
const PRICE_STATUS = ['value', 'request', 'none'];

if (!function_exists('mb_substr')) { function mb_substr($s, $start, $len = null) { return $len === null ? substr($s, $start) : substr($s, $start, $len); } }
if (!function_exists('mb_strlen')) { function mb_strlen($s) { return strlen(utf8_decode($s)); } }

/* Funktionen nach Fachbereichen (app/api/lib) */
require __DIR__ . '/kern.php';
require __DIR__ . '/nutzer.php';
require __DIR__ . '/rechte.php';
require __DIR__ . '/sicherheit.php';
require __DIR__ . '/sitzung.php';
require __DIR__ . '/oidc.php';
require __DIR__ . '/anmeldekonten.php';   // Konten der zentralen Anmeldung (Keycloak) aus der Verwaltung
require __DIR__ . '/passkey.php';
require __DIR__ . '/protokoll.php';
require __DIR__ . '/angebote.php';
require __DIR__ . '/kunden.php';
require __DIR__ . '/kundenmail.php';
require __DIR__ . '/fracht.php';
require __DIR__ . '/einzelangebote.php';
require __DIR__ . '/benachrichtigung.php';
require __DIR__ . '/postausgang.php';      // Postausgang von innen: Kundenseite legt Versandaufträge nur ab (ADR-007)
require __DIR__ . '/einkauf.php';
require __DIR__ . '/diagnose.php';
require __DIR__ . '/auswertung.php';
require __DIR__ . '/preisverlauf.php';
require __DIR__ . '/bestand.php';
require __DIR__ . '/firewall.php';
require __DIR__ . '/notfall.php';         // Notfallmodus (Modul Sicherheit): wirkt über Wartung, Sitzungen, E-Mail, Firewall
require __DIR__ . '/bereitschaft.php';    // Leitfaden, Probealarm, Wochenbericht (Modul Sicherheit)
require __DIR__ . '/integritaet.php';
require __DIR__ . '/geraete.php';
require __DIR__ . '/aktionen-liste.php';   // Aktionsregister (erzeugt aus regeln/aktionen/*.toml)
require __DIR__ . '/module-liste.php';     // Modulregister und Entscheidungstabelle (erzeugt aus regeln/)
require __DIR__ . '/module.php';
require __DIR__ . '/herkunft.php';
/* Importverträge der Daten-Eigentümer und Importzentrale (docs/plattform/schnittstellen/import.md) */
require dirname(__DIR__) . '/module/verwaltung/import.php';
require dirname(__DIR__) . '/module/bestand/import.php';
require dirname(__DIR__) . '/module/angebot/import.php';
require dirname(__DIR__) . '/module/controlling/import.php';
require dirname(__DIR__) . '/module/verwaltung/importzentrale.php';
/* Fachmodule mit eigener Oberfläche */
require dirname(__DIR__) . '/module/hr/urlaub.php';
require dirname(__DIR__) . '/module/hr/export.php';
require dirname(__DIR__) . '/module/hr/import.php';
require dirname(__DIR__) . '/module/hr/zeiterfassung.php';
require dirname(__DIR__) . '/module/crm/crm.php';
require dirname(__DIR__) . '/module/marketing/marketing.php';
require dirname(__DIR__) . '/module/controlling/controlling.php';
require dirname(__DIR__) . '/module/controlling/umsatz.php';
require dirname(__DIR__) . '/module/controlling/umsatzdaten.php';
require dirname(__DIR__) . '/module/controlling/umsatzauswertung.php';
require dirname(__DIR__) . '/module/leergut/leergut.php';
require dirname(__DIR__) . '/module/rewe/rewe.php';
require dirname(__DIR__) . '/module/rewe/export.php';
require dirname(__DIR__) . '/module/qs/qs.php';
