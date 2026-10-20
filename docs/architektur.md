# Architektur – was liegt wo

Kurzüberblick für Entwickler und KI-Sitzungen. Regeln: `AGENTS.md`. Tests: `tests/README.md`.

## Laufzeit

- **Server:** Hostinger-VPS, Docker Compose: `php:8.3-apache` (Ordner `app/` nur lesend, Daten in `daten/` →
  `/var/www/html/data`) und Caddy davor (HTTPS, Sicherheits- und Cache-Header, `Caddyfile`).
- **Auslieferung:** nur über Release: nach grüner CI auf `main` wartet der Release-Lauf auf die Freigabe des
  Inhabers (Umgebung `produktion`, `docs/release-freigabe.md`); der Server spielt per Timer ein
  (`deploy/freigabe-einspielen.sh`: Prüfung, Healthcheck, automatischer Rückfall).
- **Testumgebung:** `test.<Domain>` → Container `app-test` in `/opt/wochenangebot-test` (`deploy/testumgebung.sh`,
  `docs/testumgebung.md`); `WA_TESTUMGEBUNG=1` leitet E-Mails ins Testpostfach.
- **Daten:** Dokumente über `app/api/storage.php` – Dateien (`daten/*.php`) oder SQLite (`daten/.sqlite/store.sqlite`,
  aktiv mit `daten/.sqlite-active`, siehe `docs/datenbank.md`). Sicherung: `deploy/sichern.sh`.

## Server (`app/api/`)

| Datei | Inhalt |
| --- | --- |
| `index.php` | Einstieg: Konfiguration, Bibliotheken laden, Schreibschutz (POST/JSON), Länder-/IP-Sperre, Wartungsmodus, Aktionen einbinden |
| `lib/kern.php` | `respond()`, `fail()`, `body()`, `now()`, Eingabeprüfung `s()`, `clean_price()` |
| `lib/nutzer.php` | Mitarbeiter-Zugänge, Passwortregeln |
| `lib/rechte.php` | Nutzerrechte: Katalog `PERMS`, Rechte je Rolle (Dokument `rechte`), Ausnahmen je Nutzer (`grant`/`deny`), `user_perms`, `require_perm`, `require_perm_confirmed` |
| `lib/sitzung.php` | Mitarbeiter-Sitzung, Rollen (`require_auth` – setzt `Cache-Control: private, no-store`), Anmeldezeitpunkt `authAt` (Zwei-Faktor-Ersteinrichtung ohne Passwort nur bis 5 Minuten danach), Passwortbestätigung, CSRF; App-Betriebsart (`X-WA-Client: app`, Kennung in `X-WA-Sitzung`) |
| `lib/sicherheit.php` | Sicherheitseinstellungen, Länder-/IP-Sperre, Zwei-Faktor, Sitzungsregister, Wartungsmodus; Katalog der Passwortbestätigungen `BESTAETIGUNG` (je Aktion abschaltbar oder fest, `bestaetigung_noetig`, Gültigkeit `bestaetigung_sekunden`). Jede Bestätigungsstelle ruft `require_admin_confirmation('<aktion>')` bzw. `require_perm_confirmed('<recht>', '<aktion>')` mit ihrem Katalogschlüssel auf (der Test `bestaetigung` prüft das) |
| `lib/protokoll.php` | Protokoll (`audit`, Kundendaten-Vorgänge `LOG_KUNDENDATEN`), Änderungstexte, Anmeldeversuche (IPv6 je /64), Besucher-IP `client_ip` – `X-Forwarded-For` nur von `WA_TRUSTED_PROXIES` (Docker: `caddy`; ohne Angabe jede private Adresse) |
| `lib/angebote.php` | Angebote, Kundenpreise (`variants`, Schlüssel immer als Text – auch ältere Angebote mit Zahlen-ID), Sonderpreise (`sale`), `offer_resolve`, Datenmodell `clean_model`, Entwurfsrevisionen; neue Angebots-IDs dürfen nicht mit `e-` beginnen (Einzelangebote) und nicht nur aus Ziffern bestehen |
| `lib/kunden.php` | Kundenstammdaten, Kunden-Sitzung; freigeschaltete Angebote `customer_offers` = direkt (`customer_offers_direct`) + über die Kundengruppe (`customer_offers_gruppe`: Angebot mit der Gruppe in `gruppen` – je Gruppe höchstens eines –, sonst automatisch das Wochenangebot) |
| `lib/kundenmail.php` | E-Mails an Kunden (Vorlagen, Abmelden, Einmal-Links, Versand, Protokoll), Bestellwunsch-Vorlage |
| `lib/benachrichtigung.php` | Benachrichtigungen an Mitarbeiter: Ereignisse (`NOTIFY_EVENTS`), Einstellungen, Vormerken (`notify`, aus `audit()`), Versand nach der Antwort mit Bündelung |
| `lib/preisverlauf.php`, `lib/bestand.php` | Preisverlauf; Bestandsliste und Stammdaten (`clean_master`: Bezeichnung, Fleischart, Herkunft, Zustand, optional `vkGruppe` und `gtin`) |
| `lib/diagnose.php` | Sicherheit für IT-Administratoren: Verlauf, auffällige Adressen, Konfigurationsprüfung, nur lesende Diagnosen, CSV-Export |
| `lib/integritaet.php`, `aktionen/integritaet.php` | Dateiprüfung (Aktion `security_integrity`, nur Administrator; GET = letzter Lauf, älter als 24 h → einmal am Tag automatisch; POST `{run: true}` = jetzt): Programmdateien gegen die Prüfliste `lib/integritaet-liste.php` (Pfad → SHA-256, erzeugt von `werkzeuge/integritaet.py`, ohne `data/`), unbekannte Dateien, Datenordner (Sperrzeile, ausführbare Dateien, `.sqlite/.htaccess`), Muster in unbekannten/veränderten Dateien und gespeicherten Daten (`INTEGRITAET_MUSTER`), Komponenten (`PHP_SUPPORT_ENDE`); Ergebnis im Dokument `integritaet` (letzter Lauf + Verlauf der letzten 20), neue Befunde → `notify('sicherheit')` |
| `lib/fracht.php` | Frachtregel (Dokument `fracht`): Staffeln, `fracht_kosten` (Bestellwunsch), `fracht_hinweis` (Hinweis unter dem Angebot) |
| `lib/einzelangebote.php`, `aktionen/einzelangebote.php` | Einzelangebote für genau einen Kunden (Dokument `einzelangebote`): Prüfung, Nummern `E-JJJJ-0001`, Artikelsuche mit Bestand, Partien, erwarteten Ankünften (EK nur mit `bestand.einkaufspreise`), Merkmalen, VK-Gruppe und Wochenpreis sowie Liste der vorkommenden VK-Gruppen (`einzel_artikel`), Angebotsmodell fürs Portal (`einzel_model`, Kennung `e-<id>`, ohne Bestand, mit Kundenname und Hinweis), PDF im Design der Angebotsansicht (`einzel_pdf`, A4 quer, Logo `lib/druck-logo.jpg`), E-Mail-Vorlage als Liste oder mit PDF-Anhang; Aktionen `einzel_liste`, `einzel_detail`, `einzel_artikel`, `einzel_pdf` (Vorschau), `einzel_save`, `einzel_status`, `einzel_loeschen`, `einzel_senden` (`format`: `liste`/`pdf`; nicht für zurückgezogene oder abgelaufene Angebote) |
| `lib/pdf.php`, `lib/pdf-breiten.php` | Schlanker PDF-Erzeuger ohne Fremdbibliothek (Helvetica/WinAnsi, Text, Linien, Flächen, JPEG), Zeichenbreiten für Umbruch; nur bei Bedarf geladen |
| `lib/einkauf.php` | Fehlmengen offener Bestellwünsche gegenüber dem Bestand (`einkauf_bedarf`), E-Mail an den Einkauf |
| `orders.php`, `order_outbox.php` | Bestellverwaltung (API v1) und Versandaufträge |
| `mail.php`, `geo.php`, `storage.php` | SMTP-Client (Nachrichten mit Text/HTML, optional Anhänge als multipart/mixed), Länderdatenbank, Speicherschicht |
| `ort.php` | Ortsdatenbank (DB-IP City Lite): Laden/Umwandeln (`ort_download`, `ort_build`), Suche `ort_lookup` |
| `lib/auswertung.php`, `aktionen/auswertung.php` | Anmeldeorte der Kunden (Dokument `anmeldeorte`, 90 Tage, ohne IP), Aktionen `auswertung`, `ort_update` |
| `aktionen/*.php` | Die Aktionen (`?action=…`) nach Fachbereich: `angebote`, `kundenportal`, `mail`, `kundenverwaltung`, `zugang`, `bestand`, `einkauf`, `verwaltung`, `entwurf`, `preisverlauf`, `auswertung`, `app` (`app_info`, Mindestversion der App), `kundengruppen` (Listen der Stammdaten: Kundengruppen, VK-Gruppen und Vertreter, Dokumente `kundengruppen`/`vkgruppen`/`vertreter`, Felder je Liste in `GRUPPEN_LISTEN`, gemeinsame Prüfung `gruppen_clean` in `lib/kunden.php`; Kunden verweisen über `gruppe` und `vertreter`/`vertreter2`, Artikel der Stammdaten über `vkGruppe`) |

Aktionsdateien werden im globalen Gültigkeitsbereich eingebunden (`$action`, `$CFG`, … stehen zur Verfügung); jede Aktion
endet mit `respond()`/`fail()`. Bibliotheks- und Aktionsdateien sind nur über `index.php` nutzbar (Konstante `WA_API`).
Neue Schreibaktionen gehören in `$writeActions` (index.php), öffentliche Kundenaktionen zusätzlich in `$isPublic`
und ggf. `WARTUNG_GESPERRT`.

## Browser (`app/assets/`)

| Datei | Inhalt |
| --- | --- |
| `offer-core.js` | Gemeinsamer Kern: Excel-Leser, Angebotsparser, Vergleich (`diffOffers`), Abgleich (`mergeModels`), Sonderpreise |
| `stock-core.js` | Bestandsliste lesen (WinAB .xls/.xlsx), eingelagerte Partien und erfasste Zugänge trennen, Wochenpreise vergleichen |
| `webapp.js`, `../sw.js`, `../manifest.json`, `icons/` | Web-App: Hinweis „Zum Home-Bildschirm“, Offline-Speicher (nur Startseite, `/assets/`, öffentliches Wochenangebot; zuerst Netz), Manifest und Symbole |
| `frontend.js` + `app.css` | Angebotsseite: Filter, Merkliste, Kunden-Login, Bestellwunsch, „Meine Bestellwünsche“, Wartungsseite; `?drucken=1` öffnet den Druckdialog (aus den Einzelangeboten) |
| `admin.js` + `admin.css` | Eingabebereich: Anmeldung, Entwurf bearbeiten, gemeinsames Bearbeiten, Angebote, Veröffentlichen, Preisverlauf, Bestand, Sonderposten, Stammdaten (mit Artikelimport aus der Warenwirtschaft und Filter nach VK-Gruppe; Angebote mit Kundengruppen, `renderOffersView`, Preisimport `ofPreiseDatei`) |
| `admin-einzel.js` | Eingabebereich, Angebot bearbeiten → Einzelangebote erstellen: Übersicht, Bearbeiten, Kundenauswahl mit Suche, Fenster „Artikel hinzufügen“ (VK-Gruppen links, Artikeltabelle mit Häkchen rechts, Suche über alle Gruppen, Details mit Partien und Ankünften), Abweichungspunkt, Freigabe, Drucken/PDF (öffnet die Angebotsseite `?angebot=e-<id>&drucken=1` mit deren Druckdialog), E-Mail als Liste oder PDF-Anhang, Knöpfe in der Kopfleiste (nutzt `window.WA`) |
| `admin-verwaltung.js` | Eingabebereich, Verwaltung: Nutzer, Bestellungen, Einkauf, Kunden (mit CSV-Import aus der Warenwirtschaft, `kunden_import`), Listen der Stammdaten (`gruppenListe` mit Feldern je Liste: Kundengruppen, VK-Gruppen, Vertreter; CSV-Leser `W.csvZeilen`/`W.csvText`), E-Mail, Protokoll, Sicherheit (nutzt `window.WA` aus `admin.js`) |

Dunkle Farben (`prefers-color-scheme: dark`, `data-theme="dark"`) gelten nur für `@media screen` – der Druck ist immer hell. Druckregeln: Angebotsseite in `app.css` (`#print-root`), Eingabebereich in `admin.css` (geöffnete Ansicht bzw. offenes Fenster).

Schriften liegen in `app/assets/fonts/` (Geist, Geist Mono; Lizenz daneben), eingebunden in `app.css`. Kein Build-Schritt. Nach Änderungen an `app/assets/` die Versionsnummern setzen: `python3 werkzeuge/asset_versionen.py --setzen`. Danach (nach jeder Änderung unter `app/`) die Prüfliste der Dateiprüfung erneuern: `python3 werkzeuge/integritaet.py --setzen` (die CI prüft beides).

## App (`mobile/`)

Expo/React Native (TypeScript) für iOS und Android, eigener Build (`npm ci`), wird nicht auf den Server ausgeliefert
(der Container bindet nur `app/` ein). Nutzt die Schnittstelle wie die Website, Sitzung über die Kopfzeile
`X-WA-Sitzung` ([app-api.md](app-api.md)). `offer-core.js` wird mitgebündelt (Metro `watchFolders`), damit
Merklisten-Schlüssel identisch sind. Aufbau und Veröffentlichung: [mobile/LIESMICH.md](../mobile/LIESMICH.md).

## Tests

Bestandsdaten, exakte Wochenpreise, ETA-Quelle und kompatible Erweiterungen:
[Bestand: Wochenpreise und Zugänge](bestand-wochenpreise.md).

- `tests/run_e2e.py` startet je Testgruppe einen frischen PHP-Server mit Testdaten (`tests/fixtures/`), parallel mit
  eigenen Ports (`WA_JOBS`). Tests holen Adressen aus `tests/e2e/umgebung.py`; Hilfen: `kunden_hilfe.Client`,
  `auth_helpers`, `wait_text()`, `until()`, `shot()`, Test-Mailserver `smtp_test.TestSmtp`.
- App: `cd mobile && npm test` (Jest), `npm run typecheck`, `npm run export:native`; Gruppe `app_web` testet den Web-Build der App gegen den Testserver (nur wenn `mobile/dist-web` gebaut ist).
- `tests/unit/*.test.js` (Node), `tests/deploy/*` (Sicherung, Release-Modus, Release-Prüfungen, Datenbank, Testumgebung).
- CI (`.github/workflows/ci.yml`): Syntax, Versionsnummern, Prüfliste der Dateiprüfung, Ports, Secrets, Abhängigkeiten, E2E in beiden Speicherarten.
