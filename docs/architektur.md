# Architektur – was liegt wo

Kurzüberblick für Entwickler und KI-Sitzungen. Regeln: `AGENTS.md`. Tests: `tests/README.md`.

Ziel und Umbau zur STAFL-Plattform: `docs/plattform/`. Welche Datei, welches Speicher-Dokument und welches Recht zu
welchem Modul gehört, steht in `regeln/` (`python3 werkzeuge/regeln.py modul <id>`).

## Laufzeit

- **Server:** Hostinger-VPS, Docker Compose: `php:8.3-apache` (Ordner `app/` nur lesend, Daten in `daten/` →
  `/var/www/html/data`) und Caddy davor (HTTPS, Sicherheits- und Cache-Header, `Caddyfile`; versionierte Skripte/Stylesheets `/assets/…?v=…` ein Jahr `immutable`, alles andere `no-cache`; die Nummern setzt der
  Server beim Einspielen, siehe „Bereitstellung“).
- **Anwendungs-Image (vorbereitet, nicht im Betrieb):** `deploy/image/Dockerfile` = `php:8.3-apache` (fest über Digest) plus
  mod_auth_openidc, installiert, aber nicht geladen – Voraussetzung für die zentrale Anmeldung (ADR-003). Die CI baut es
  und prüft mit `deploy/image/pruefen.sh`, dass es sich ohne Konfiguration genau wie das Grundimage verhält
  (Apache-Module, PHP-Erweiterungen, Antworten, Sicherheitskopfzeilen); kritische Lücken blockieren. Umstellung von
  `docker-compose.yml` ist ein eigener Schritt mit Freigabe (eine Änderung dort startet die Container beim Release neu).
- **Zentrale Anmeldung (vorbereitet, nicht aktiv):** `deploy/anmeldung/` – Compose-Ergänzung (App mit Anwendungs-Image,
  Keycloak 26.8.1, eigene PostgreSQL; nur `127.0.0.1` bzw. internes Netz), Apache-Hosts, Caddy-Teil, Realm (erzeugt von
  `werkzeuge/realm_produktion.py` aus dem Test-Realm). Geprüft in der CI (`deploy/anmeldung/pruefen.sh`); Ablaufplan mit
  Freigaben: `docs/plattform/inbetriebnahme-anmeldung.md`. Geheimnisse und Realm-Import nur auf dem Server (`daten-anmeldung/`).
- **Auslieferung:** nur über Release: nach grüner CI auf `main` wartet der Release-Lauf auf die Freigabe des
  Inhabers (Umgebung `produktion`, `docs/release-freigabe.md`); der Server spielt per Timer ein
  (`deploy/freigabe-einspielen.sh`: Prüfung, Healthcheck, automatischer Rückfall).
- **Bereitstellung** (`deploy/bereitstellen.py`): nach jedem Codewechsel (Release, Rückfall, Testumgebung, Einrichtung; zusätzlich
  bei jedem Lauf von `aktualisieren.sh`, falls etwas fehlt) aus den Git-Objekten genau des aktiven Commits: Versionsnummern
  `?v=<SHA-256 des Inhalts, 10 Zeichen>` in den HTML-Seiten und die Prüfliste `app/api/lib/integritaet-liste.php`. Beides
  steht nicht im Repository (keine Merge-Konflikte mehr). Ohne Nummer lädt der Browser mit Rückfrage (`no-cache`) – nie
  eine veraltete Kopie. Ältere Stände, die Liste und Nummern noch selbst enthalten, bleiben unverändert (Rückfall).
- **Testumgebung:** `test.<Domain>` → Container `app-test` in `/opt/wochenangebot-test` (`deploy/testumgebung.sh`,
  `docs/testumgebung.md`); `WA_TESTUMGEBUNG=1` leitet E-Mails ins Testpostfach.
- **Daten:** Dokumente über `app/api/storage.php` – Dateien (`daten/*.php`) oder SQLite (`daten/.sqlite/store.sqlite`,
  aktiv mit `daten/.sqlite-active`, siehe `docs/datenbank.md`). Sicherung: `deploy/sichern.sh`.

## Server (`app/api/`)

| Datei | Inhalt |
| --- | --- |
| `index.php` | Einstieg: Konfiguration, Bibliotheken laden, Schreibschutz (POST/JSON), Länder-/IP-Sperre, Wartungsmodus, Aktionen einbinden |
| `lib/kern.php` | `respond()`, `fail()`, `body()`, `now()`, Eingabeprüfung `s()`, `clean_price()` |
| `lib/nutzer.php` | Mitarbeiter-Zugänge (optional `vorname`, `nachname`, `email`, `mailInfo`, `twofaPflicht` – einzeln verpflichteter zweiter Faktor, nur Administratoren über `user_save`, wirkt über `twofa_required` in `lib/sicherheit.php`; `name` bleibt für Anzeige und ältere Clients), Benutzername aus Vor-/Nachname (`benutzername_vorschlag`), Prüfung `nutzer_person`, Passwortregeln, E-Mail mit Zugangsdaten (`mail_tpl_nutzer`, Aktion `user_mail` in `aktionen/verwaltung.php`) |
| `lib/rechte.php` | Nutzerrechte: Katalog `PERMS`, Rechte je Rolle (Dokument `rechte`), Ausnahmen je Nutzer (`grant`/`deny`), `user_perms`, `require_perm`, `require_perm_confirmed` |
| `lib/sitzung.php` | Mitarbeiter-Sitzung (Cookie über HTTPS `__Host-WA_ADMIN`, über HTTP `WA_ADMIN`; ein altes Cookie ohne Präfix wird über HTTPS nicht gelesen, sondern gelöscht – `sitzung_cookie_name()`, GR-108), Rollen (`require_auth` – setzt `Cache-Control: private, no-store`), Anmeldezeitpunkt `authAt` (Zwei-Faktor-Ersteinrichtung ohne Passwort nur bis 5 Minuten danach), Passwortbestätigung, CSRF; App-Betriebsart (`X-WA-Client: app`, Kennung in `X-WA-Sitzung`) |
| `lib/sicherheit.php` | Sicherheitseinstellungen, Länder-/IP-Sperre, Zwei-Faktor, Sitzungsregister, Wartungsmodus; Katalog der Passwortbestätigungen `BESTAETIGUNG` (je Aktion abschaltbar oder fest, `bestaetigung_noetig`, Gültigkeit `bestaetigung_sekunden`). Jede Bestätigungsstelle ruft `require_admin_confirmation('<aktion>')` bzw. `require_perm_confirmed('<recht>', '<aktion>')` mit ihrem Katalogschlüssel auf (der Test `bestaetigung` prüft das) |
| `lib/protokoll.php` | Protokoll (`audit`, Kundendaten-Vorgänge `LOG_KUNDENDATEN`), Änderungstexte, Anmeldeversuche (IPv6 je /64), Besucher-IP `client_ip` – `X-Forwarded-For` nur von `WA_TRUSTED_PROXIES` (Docker: `caddy`; ohne Angabe jede private Adresse) |
| `lib/passkey.php`, `aktionen/passkey.php` | Passkeys (WebAuthn) ohne Fremdbibliothek: kleiner CBOR-Leser, COSE-Schlüssel (ES256/RS256) → PEM, Prüfung von clientDataJSON (Art, Challenge, Herkunft = aufgerufener Host) und Authenticator-Daten (rpIdHash, UP+UV, Zähler), Signatur mit `openssl_verify`; gespeichert im optionalen Nutzerfeld `passkeys`; `has_second_factor` (App oder Passkey) für Zwei-Faktor-Pflicht und Anmeldung. Aktionen `passkey_list`, `passkey_begin`, `passkey_register`, `passkey_rename`, `passkey_delete` (eigene Passkeys, Passwort wie bei der Authenticator-App), `passkey_login_begin`, `passkey_login` (ohne Benutzername oder mit `second` als zweiter Schritt; nicht in der App) |
| `lib/geraete.php` | Vertraute Geräte: Cookie `__Host-WA_GERAET` (über HTTP ohne Präfix; zufällige Kennung, eine vorhandene nur für den eigenen Zugang weiterverwendet), beim Zugang (`geraete`: Prüfsumme, Name, seit, zuletzt, Fehlerzähler `f`, höchstens 10, Verfall 180 Tage). `geraet_vertraut` (während einer Sperre normale Prüfung, Fehler je Gerät), `geraet_merken` nach jeder erfolgreichen Anmeldung (Passwort, Code, Passkey, Kunde), `geraete_zuruecksetzen` bei Passwortwechsel, `geraet_neu_melden` (Sicherheitsereignis bei Administrator-Anmeldung von neuem Gerät) |
| `lib/protokoll.php` | Protokoll (`audit`), Änderungstexte, Anmeldeversuche |
| `lib/angebote.php` | Angebote, Kundenpreise (`variants`, Schlüssel immer als Text – auch ältere Angebote mit Zahlen-ID), Sonderpreise (`sale`), `offer_resolve`, Datenmodell `clean_model`, Entwurfsrevisionen; neue Angebots-IDs dürfen nicht mit `e-` beginnen (Einzelangebote) und nicht nur aus Ziffern bestehen |
| `lib/kunden.php` | Kundenstammdaten, Kunden-Sitzung; freigeschaltete Angebote `customer_offers` = direkt (`customer_offers_direct`) + über die Kundengruppe (`customer_offers_gruppe`: Angebot mit der Gruppe in `gruppen` – je Gruppe höchstens eines –, sonst automatisch das Wochenangebot) |
| `lib/kundenmail.php` | E-Mails an Kunden (Vorlagen, Abmelden, Einmal-Links, Versand, Protokoll), Bestellwunsch-Vorlage |
| `lib/benachrichtigung.php` | Benachrichtigungen an Mitarbeiter: Ereignisse (`NOTIFY_EVENTS`), Einstellungen, Vormerken (`notify`, aus `audit()`), Versand nach der Antwort mit Bündelung |
| `lib/preisverlauf.php`, `lib/bestand.php` | Preisverlauf; Bestandsliste und Stammdaten (`clean_master`: Bezeichnung, Fleischart, Herkunft, Zustand, optional `vkGruppe` und `gtin`) |
| `lib/bestand-pdf.php` | Bestand als PDF (Aktion `stock_pdf`, Recht „Bestand ansehen“, POST mit CSRF): Reihenfolge und Warengruppen aus der Ansicht (`rows`: `{g}`/`{c}`), Mengen und MHD aus dem gespeicherten Bestand; A4 hoch mit Logo, Legende, Gruppen- und Gesamtsummen, „Seite x von y“; ohne Preise, erfassten Bestand, Gesamt verfügbar und Zugänge. Nutzt `lib/pdf.php`. Partien und Zugänge tragen optional `marke` (Import: `stock-core.js`, Spalte neben der Überschrift „Marke“) |
| `lib/diagnose.php` | Sicherheit für IT-Administratoren: Verlauf, auffällige Adressen, Konfigurationsprüfung, nur lesende Diagnosen, CSV-Export |
| `lib/oidc.php` | Zentrale Anmeldung über Keycloak (ADR-003, GR-110), heute nur in der CI-Testumgebung `tests/oidc/`: aktiv nur, wenn der Webserver `WA_OIDC=1` setzt. OpenID Connect spricht das Apache-Modul mod_auth_openidc; die Anwendung liest die geprüfte Identität nur aus Server-Umgebungsvariablen (`REMOTE_USER`, `OIDC_CLAIM_*`, Aussteller gegen `WA_OIDC_ISSUER`), verknüpft sie mit dem Mitarbeiterkonto (`oidcSub`), prüft Rolle/Rechte/„aktiv“ wie bisher und hält je Host eine eigene PHP-Sitzung für CSRF und Sitzungsregister. Verlangt die Anmeldestärke `acr` = `WA_OIDC_ACR` (Standard `mfa`, zweiter Faktor). Sensible Aktionen: statt Passwortbestätigung erneute Anmeldung bei Keycloak (`reauth_required` mit Adresse, `max_age=0`), bestätigt durch den neuen Anmeldezeitpunkt. Eigene Anmeldeverfahren (Registerfeld `lokale_anmeldung`) sind dort gesperrt; Abmelden über Keycloak (`abmelden`-Adresse, Back-Channel-Logout an alle Anwendungen) |
| `module/verwaltung/importzentrale.php`, `aktionen/importzentrale.php` | Importzentrale (Verwaltung → Import, Roadmap 10b): Registrierung aller Importarten aus den Importverträgen der Eigentümer (`IMPORT_EIGENTUEMER`), einheitliche Prüfung (Anmeldung, Recht je Importart, Wartung der Oberfläche der Importaktion, Passwortbestätigung), Aufruf von Vorschau/Übernahme des Eigentümers, Begrenzung auf 500 Vorschauzeilen. Aktionen `import_arten`, `import_pruefen`, `import_uebernehmen`. Liest und schreibt selbst keine Daten. Vertrag: [schnittstellen/import.md](plattform/schnittstellen/import.md) |
| `module/<modul>/import.php` | Importverträge der Daten-Eigentümer: `verwaltung` (Kunden `kunden_import_lauf`, Kundengruppen/VK-Gruppen/Vertreter `gruppen_speichern`, Artikelstammdaten `stammdaten_speichern`), `bestand` (`bestand_speichern`), `angebot` (Preisverlauf `preisverlauf_woche_speichern`; Wochenangebot und Artikelpreise nur als Verweis auf den Editor). Die bisherigen Aktionen (`kunden_import`, `*_save`, `master_save`, `stock_import`, `history_import`) nutzen dieselben Funktionen |
| `lib/module.php`, `lib/module-liste.php`, `aktionen/module.php` | Modulzustand zur Laufzeit (GR-102): `module-liste.php` ist aus `regeln/module.toml` und `regeln/wartung.toml` erzeugt (`werkzeuge/regeln.py erzeugen`: Module, Oberflächen, Entwicklungsstand, Freigabe, Entscheidungstabelle – ohne Code-Pfade/Agenten); `module.php` wertet nur diese Tabelle aus (`modul_entscheiden`, `modul_zustand`, `modul_uebersicht`; Betrieb heute: bisheriger Wartungsmodus = `angebot.kunden` in Wartung). Aktion `module_status` (angemeldet, nur lesend; Verlauf nur für Administratoren) für Dashboard und Modulverwaltung. Wartung je Oberfläche: Dokument `module` (`wartung` je `<modul>.<oberfläche>` mit Grund, Hinweis, `ab` = geplanter Beginn, `until` = Hinweis; `verlauf` der letzten 100 Änderungen); `angebot.kunden` weiter über das Dokument `wartung`. Freigabe und Tester zur Laufzeit (Modulverwaltung): `freigabe` und `tester` im Dokument `module`, `modul_freigabe` (Startwert Register, Änderung nur innerhalb `MODUL_FREIGABE_ERLAUBT`; nicht änderbar: produktive und nicht sperrbare Oberflächen), `modul_person` (bei Testfreigabe nur eingetragene Tester, Administratoren nur eingetragen); Aktionen `modul_freigabe_save`, `modul_tester_save` (Administrator, immer mit Bestätigung); Oberfläche Sicherheit → Module (`admin-verwaltung.js`, `#mv-box`). `modul_durchsetzen` im Einstieg weist Aktionen einer gesperrten Oberfläche mit 503 ab (außer `wartung_frei`); `modul_wartung_save` (Administrator, immer mit Bestätigung). Notfall: `deploy/wartung-aus.sh` |
| `lib/integritaet.php`, `aktionen/integritaet.php` | Dateiprüfung (Aktion `security_integrity`, nur Administrator; GET = letzter Lauf, älter als 24 h → einmal am Tag automatisch; POST `{run: true}` = jetzt): Programmdateien gegen die Prüfliste `lib/integritaet-liste.php` (Pfad → SHA-256, bei HTML-Seiten `[mit, ohne Versionsnummern]`; beim Einspielen aus dem freigegebenen Commit erzeugt von `deploy/bereitstellen.py`, nicht im Repository, ohne `data/`), unbekannte Dateien, Datenordner (Sperrzeile, ausführbare Dateien, `.sqlite/.htaccess`), Muster in unbekannten/veränderten Dateien und gespeicherten Daten (`INTEGRITAET_MUSTER`), Komponenten (`PHP_SUPPORT_ENDE`); Ergebnis im Dokument `integritaet` (letzter Lauf + Verlauf der letzten 20), neue Befunde → `notify('sicherheit')` |
| `lib/herkunft.php` | Herkunftsprüfung als erster Schritt im Einstieg (GR-109): `Sec-Fetch-Site` same-site/cross-site → 403 (auch von Nachbar-Subdomains wie `test.angebot-stafl.de`), bei Anfragen außer GET/HEAD muss ein mitgesendeter `Origin` genau `Schema://Host` sein (`is_https()` wie bei Passkeys). Ohne diese Kopfzeilen (App, Server-zu-Server) gilt der bisherige Schutz. Ausnahme nur über das Registerfeld `fremde_herkunft` (heute `abmelden1`, RFC 8058). Abweisungen zählen nicht für die Firewall (eine fremde Seite darf ihre Besucher nicht sperren lassen) |
| `lib/firewall.php`, `aktionen/schutz.php` | Schutzzentrale: `fw_guard` vor jeder Aktion (Sperrliste → Firewall-Muster `FW_MUSTER`/`FW_WERKZEUGE` → Fehlerbremse und Live-Verkehr nach der Aktion), Falle `waf_probe` (Caddy/.htaccess leiten Pfade wie /wp-login.php dorthin), automatische Sperre, Bedrohungsliste (Spamhaus DROP; im selben Dokument ein Index für die Prüfung vor jeder Anfrage: IPv4 als sortierte Bereiche, binäre Suche – `fw_feed_index`/`fw_feed_trifft`, fehlt er, wird er nachgebaut), Vorlagen (`FW_VORLAGEN`, Prüfung über `sec_clean`), Export/Import. Dokumente `firewall`, `sperrliste`, `bedrohungsliste`, `fw_zaehler`, `verkehr` (Ringpuffer 500); geschrieben wird nur bei Auffälligkeiten oder während eines Mitschnitts. Oberfläche: `assets/admin-schutz.js` |
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
Jede Aktion steht im Aktionsregister `regeln/aktionen/<modul>.toml` (Modul, Oberfläche, `schreibend`, `oeffentlich`,
`kunden_wartung`; Erklärung `regeln/aktionen/LIESMICH.md`). `python3 werkzeuge/regeln.py erzeugen` schreibt daraus
`lib/aktionen-liste.php` (Konstante `AKTIONEN`), nach der `index.php` Schreibschutz (POST/JSON), öffentlichen Bereich
(IP-/Ländersperre) und Wartungsmodus anwendet. Die CI lehnt nicht registrierte oder verwaiste Aktionen ab.

## Browser (`app/assets/`)

| Datei | Inhalt |
| --- | --- |
| `offer-core.js` | Gemeinsamer Kern: Excel-Leser, Angebotsparser, Vergleich (`diffOffers`), Abgleich (`mergeModels`), Sonderpreise |
| `stock-core.js` | Bestandsliste lesen (WinAB .xls/.xlsx), eingelagerte Partien und erfasste Zugänge trennen, Wochenpreise vergleichen |
| `webapp.js`, `../sw.js`, `../manifest.json`, `icons/` | Web-App: Hinweis „Zum Home-Bildschirm“, Offline-Speicher (nur Startseite, `/assets/`, öffentliches Wochenangebot; zuerst Netz), Manifest und Symbole |
| `frontend.js` + `app.css` | Angebotsseite: Filter, Merkliste, Kunden-Login, Bestellwunsch, „Meine Bestellwünsche“, Wartungsseite; `?drucken=1` öffnet den Druckdialog (aus den Einzelangeboten) |
| `admin.js` + `admin.css` | Eingabebereich (unter der zentralen Anmeldung je Host nur die Ansichten seines Bereichs `me.bereich` = `WA_OBERFLAECHE`: `BEREICH_VIEWS` für `angebot.eingabe`, `verwaltung.verwaltung`, `bestand.intern` – nur Anzeige, Rechte prüft der Server; Startansicht aus der Adresse `?ansicht=<id>` oder `#<id>`, nur erlaubte Ansichten): Anmeldung, Entwurf bearbeiten, gemeinsames Bearbeiten, Angebote, Veröffentlichen, Preisverlauf, Bestand, Sonderposten, Stammdaten (mit Artikelimport aus der Warenwirtschaft und Filter nach VK-Gruppe; Angebote mit Kundengruppen, `renderOffersView`, Preisimport `ofPreiseDatei`) |
| `admin-einzel.js` | Eingabebereich, Angebot bearbeiten → Einzelangebote erstellen: Übersicht, Bearbeiten, Kundenauswahl mit Suche, Fenster „Artikel hinzufügen“ (VK-Gruppen links, Artikeltabelle mit Häkchen rechts, Suche über alle Gruppen, Details mit Partien und Ankünften), Abweichungspunkt, Freigabe, Drucken/PDF (öffnet die Angebotsseite `?angebot=e-<id>&drucken=1` mit deren Druckdialog), E-Mail als Liste oder PDF-Anhang, Knöpfe in der Kopfleiste (nutzt `window.WA`) |
| `admin-import.js` + `admin-import.css` | Eingabebereich, Verwaltung → Import (Ansicht `importe`): Importzentrale – Liste der Importarten aus `import_arten`, einheitliche Vorprüfung der Datei (Endung, leer, UTF-16, Excel statt CSV), Leser des Eigentümers aus `window.WA.importLeser` (registriert in `admin.js`: Artikelstammdaten, Bestand, Preisverlauf; in `admin-verwaltung.js`: Kunden, Kundengruppen, VK-Gruppen, Vertreter), Vorschau mit Zahlen, Hinweisen, Zeilen je Art und Filter, Übernahme, Ergebnis |
| `admin-verwaltung.js` | Eingabebereich, Verwaltung: Nutzer, Bestellungen, Einkauf, Kunden (mit CSV-Import aus der Warenwirtschaft, `kunden_import`), Listen der Stammdaten (`gruppenListe` mit Feldern je Liste: Kundengruppen, VK-Gruppen, Vertreter; CSV-Leser `W.csvZeilen`/`W.csvText`), E-Mail, Protokoll, Sicherheit (nutzt `window.WA` aus `admin.js`) |

Dunkle Farben (`prefers-color-scheme: dark`, `data-theme="dark"`) gelten nur für `@media screen` – der Druck ist immer hell. Druckregeln: Angebotsseite in `app.css` (`#print-root`), Eingabebereich in `admin.css` (geöffnete Ansicht bzw. offenes Fenster).

Schriften liegen in `app/assets/fonts/` (Geist, Geist Mono; Lizenz daneben), eingebunden in `app.css`. Kein Build-Schritt. Skripte und Stylesheets werden in den HTML-Seiten **ohne** `?v=` eingebunden; Versionsnummern und Prüfliste der Dateiprüfung erzeugt der Server beim Einspielen (`deploy/bereitstellen.py`). Die CI prüft, dass alle Einbindungen existieren und keine Nummern bzw. keine Prüfliste im Repository stehen (`werkzeuge/asset_versionen.py`, `werkzeuge/integritaet.py`); `--zeigen` zeigt, was der Server erzeugen würde.

## App (`mobile/`)

Expo/React Native (TypeScript) für iOS und Android, eigener Build (`npm ci`), wird nicht auf den Server ausgeliefert
(der Container bindet nur `app/` ein). Nutzt die Schnittstelle wie die Website, Sitzung über die Kopfzeile
`X-WA-Sitzung` ([app-api.md](app-api.md)). `offer-core.js` wird mitgebündelt (Metro `watchFolders`), damit
Merklisten-Schlüssel identisch sind. Aufbau und Veröffentlichung: [mobile/LIESMICH.md](../mobile/LIESMICH.md).

## Dashboard (`dashboard/`)

Mitarbeiter-Dashboard der STAFL-Plattform (Roadmap PR 6): `index.html`, `dashboard.css`, `dashboard.js`, ohne Inline-Skript.
Liest `status` und `module_status` und zeigt die acht Kacheln in der Reihenfolge des Modulregisters – keine fest
programmierte Liste. Status je Kachel (Verfügbar, Wartung, Entwicklungsstand …) kommt aus `modul_zustand`; die Kachel ist
nur Anzeige, gesperrt wird serverseitig (GR-102, GR-103). Liegt bewusst **außerhalb** von `app/` und wird daher nicht
ausgeliefert; `dashboard-stafl.de` bleibt 503-Platzhalter (GR-105), bis die Anmeldung über Keycloak (ADR-003, PR 7) steht
und der Inhaber die Freigabe erteilt. Der Testlauf blendet den Ordner nur in der Gruppe `dashboard` unter `/dashboard/` ein
(`ZUSATZ` in `tests/run_e2e.py`). Hell/Dunkel mit demselben Speicherschlüssel wie die Angebotsseite.

## Tests

Bestandsdaten, exakte Wochenpreise, ETA-Quelle und kompatible Erweiterungen:
[Bestand: Wochenpreise und Zugänge](bestand-wochenpreise.md).

- `tests/run_e2e.py` startet je Testgruppe einen frischen PHP-Server mit Testdaten (`tests/fixtures/`), parallel mit
  eigenen Ports (`WA_JOBS`). Tests holen Adressen aus `tests/e2e/umgebung.py`; Hilfen: `kunden_hilfe.Client`,
  `auth_helpers`, `wait_text()`, `until()`, `shot()`, Test-Mailserver `smtp_test.TestSmtp`.
- App: `cd mobile && npm test` (Jest), `npm run typecheck`, `npm run export:native`; Gruppe `app_web` testet den Web-Build der App gegen den Testserver (nur wenn `mobile/dist-web` gebaut ist).
- `tests/unit/*.test.js` (Node), `tests/deploy/*` (Sicherung, Release-Modus, Release-Prüfungen, Datenbank, Testumgebung).
- CI (`.github/workflows/ci.yml`): Syntax, Regelwerk und Modulgrenzen (`werkzeuge/regeln.py`), Einbindungen ohne Versionsnummern, Prüfliste nicht im Repository, Ports, Secrets, Abhängigkeiten, E2E in beiden Speicherarten (je 3 Teile, `WA_TEIL`). Auf `main` Übernahme der Prüfung aus dem Pull Request bei gleichem Inhalt (`.github/scripts/ci_nachweis.py`); Paketvorrat und Downloads im Zwischenspeicher (`zwischenspeicher.yml`, `.github/scripts/testumgebung.sh`, `apt_vorrat.py`); Trockenlauf des Nachweises: `ci-nachweis.yml`.
