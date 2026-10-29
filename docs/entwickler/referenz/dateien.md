# Referenz: Dateien

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: versionierte Dateien, regeln/module.toml, Kopfkommentare. Die CI prüft, dass diese Datei zum Code passt. -->

Jede Code-Datei beginnt mit einem Kopfkommentar; dessen erste Aussage steht hier. Ausführlicher: [../architektur.md](../../architektur.md) und die Kapitel dieser Dokumentation.

## Wurzel

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `.env.example` | plattform | – |
| `.gitignore` | plattform | – |
| `.gitleaks.toml` | plattform | Secret-Scan (gitleaks) |
| `AGENTS.md` | plattform | Arbeitsregeln für Entwickler und KI-Agenten |
| `CLAUDE.md` | plattform | Hinweis für Claude-Sitzungen |
| `Caddyfile` | plattform | HTTPS-Zertifikat wird automatisch geholt und verlängert (Let's Encrypt) |
| `LIESMICH.md` | plattform | Wochenangebot – angebot-stafl.de |
| `docker-compose.yml` | plattform | Wochenangebot – Start: docker compose up -d |

## `.github/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `pull_request_template.md` | plattform | Was ändert sich (für Anwender) |

## `.github/scripts/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `apt_vorrat.py` | plattform | Paketvorrat für die CI: heruntergeladene Debian-Pakete (.deb) zwischen Läufen aufbewahren. |
| `ci_nachweis.py` | plattform | Nachweis „schon im Pull Request vollständig geprüft“ für einen Commit auf main (ci.yml, Auftrag „nachweis“). |
| `release-pruefen.sh` | plattform | Prüfungen des Release-Laufs (.github/workflows/release.yml). |
| `testumgebung.sh` | plattform | Testumgebung der CI einrichten (ci.yml |

## `.github/workflows/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `ci-nachweis.yml` | plattform | Trockenlauf des Nachweises „schon im Pull Request vollständig geprüft“ (ci.yml, Auftrag „nachweis“): zeigt für einen Commit auf main, ob die CI dort die schweren Aufträge überspringen würde und warum (nicht). |
| `ci.yml` | plattform | Automatische Prüfungen für jeden Pull Request und jeden Commit auf main. |
| `release.yml` | plattform | Produktive Freigabe. Nach jedem erfolgreichen CI-Lauf auf main startet die CI diesen Lauf automatisch; er wartet dann auf die Freigabe in der GitHub-Umgebung „produktion“ (E-Mail/App |
| `zwischenspeicher.yml` | plattform | Füllt den GitHub-Zwischenspeicher für die Testaufträge der CI (ci.yml |

## `app/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `.htaccess` | plattform | – |
| `index.html` | angebot | Seite „Wochenangebot“ |
| `sw.js` | angebot | Web-App (zum Home-Bildschirm hinzugefügt) |

## `app/admin/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `.htaccess` | angebot | – |
| `bestaetigt.html` | angebot | Rücksprung nach der erneuten Anmeldung im eigenen Fenster (admin.js: bestaetigenPerFenster): meldet dem Eingabebereich „bestätigt“ und schließt sich. |
| `index.html` | angebot | Anmeldung / Ersteinrichtung |

## `app/api/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `config.php` | plattform | Einstellungen für die Wochenangebots-API. |
| `geo.php` | plattform | Länderzuordnung von IP-Adressen (für Ländersperren) Datenquelle: ip-location-db „geo-whois-asn-country“ (CC0 / Public Domain) Binärformat laender.dat.php (beginnt mit einer PHP-Sperre, damit die Datei im Browser … |
| `index.php` | plattform | API-Einstieg der STAFL-Plattform (/api/?action=…): prüft jede Anfrage (Herkunft, Host, Schreibschutz, Sperren, Wartung, Modulzugang) und bindet die Aktionen aus aktionen/*.php ein. |
| `mail.php` | plattform | E-Mail-Versand über einen SMTP-Server (z. |
| `order_outbox.php` | angebot | Durable per-recipient jobs live in the same document/transaction as the order. |
| `orders.php` | angebot | Shared order operations for the website and future app clients. |
| `ort.php` | verwaltung | Ungefährer Ort (Stadt) einer IP-Adresse – für die Karte der Kunden-Anmeldungen (Auswertung) Datenquelle |
| `storage.php` | plattform | Shared persistence for HTTP and maintenance tools. |

## `app/api/aktionen/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `angebote.php` | angebot | Aktionen: Angebote (öffentlich und Eingabebereich) Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |
| `anmeldekonten.php` | plattform | Aktionen: Konten der zentralen Anmeldung (Keycloak) aus Verwaltung → Mitarbeiter (nur Administratoren). anmeldekonto (lesen) |
| `app.php` | plattform | Aktionen: Grunddaten für die App (iOS/Android, Ordner mobile/). |
| `auswertung.php` | verwaltung | Aktionen: Auswertung (Karte der Kunden-Anmeldungen) und Aktualisieren der Ortsdaten Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |
| `bestand.php` | bestand | Aktionen: Bestand und Stammdaten Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |
| `controlling.php` | controlling | Aktionen: Controlling (Oberfläche controlling.intern, Fachlogik in app/api/module/controlling/) Rechte (GR-103): controlling.zugang – Modul öffnen (Register, standardmäßig niemand); controlling.umsatz_sehen – … |
| `crm.php` | crm | Aktionen: CRM · Vertrieb (Oberfläche crm.intern, Daten und Regeln in app/api/module/crm/crm.php) Rechte (GR-103): crm.sehen – Kunden, Kundenblätter, Wiedervorlagen, Pipeline, Auswertung, Karte ansehen (crm_karte); … |
| `einkauf.php` | einkauf | Aktionen: Einkauf (Fehlmengen aus offenen Bestellwünschen) Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |
| `einzelangebote.php` | angebot | Aktionen: Einzelangebote (Angebot bearbeiten → Einzelangebote). |
| `entwurf.php` | angebot | Aktionen: Entwurf, gemeinsames Bearbeiten, Veröffentlichen, Versionen Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |
| `hr.php` | hr | Aktionen: HR · Urlaubsverwaltung (Oberfläche hr.intern, Logik in app/api/module/hr/) Rechte (GR-103): hr.antrag – eigener Urlaub, Anträge, Abwesenheitskalender (nur „abwesend“); hr.genehmigen – Urlaubsanträge … |
| `importzentrale.php` | verwaltung | Aktionen: Importzentrale (Verwaltung → Import; Ablauf und Prüfungen: module/verwaltung/importzentrale.php) GET import_arten Importarten, für die der angemeldete Nutzer das Recht hat (Anzeige ist keine Berechtigung) … |
| `integritaet.php` | plattform | Aktion: Dateiprüfung (lib/integritaet.php) – nur Administratoren. |
| `kundengruppen.php` | verwaltung | Aktionen: Listen der Stammdaten – Kundengruppen, VK-Gruppen und Vertreter (Beschreibung: lib/kunden.php). |
| `kundenportal.php` | angebot | Aktionen: Kunden auf der Angebotsseite |
| `kundenverwaltung.php` | verwaltung | Aktionen: Kundenstammdaten (Administrator) Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |
| `mail.php` | plattform | Aktionen: E-Mail-Versand (Administrator) Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |
| `marketing.php` | marketing | Aktionen: Marketing · Redaktionsplan (Oberfläche marketing.intern, Daten und Regeln in app/api/module/marketing/marketing.php) Rechte (GR-103): marketing.sehen – Übersicht, Kalender, Board, Liste, Kampagnen ansehen, … |
| `module.php` | plattform | Modulübersicht (Plattformkern) |
| `passkey.php` | plattform | Aktionen: Passkeys (WebAuthn) – eigene Passkeys verwalten, Anmeldung mit Passkey Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |
| `preisverlauf.php` | angebot | Aktionen: Preisverlauf Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |
| `schutz.php` | plattform | Schutzzentrale (Verwaltung → Schutz, nur Administratoren) |
| `sicherheit.php` | sicherheit | Aktionen des Moduls Sicherheit (Oberfläche sicherheit.intern, sicherheit.dashboard-stafl.de; docs/plattform/modul-sicherheit.md) |
| `verwaltung.php` | plattform | Aktionen: Sicherheit, Länder-/IP-Sperre, Sitzungen (Oberfläche Modul Sicherheit), Betriebszustand, Nutzer, Protokoll Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit … |
| `zugang.php` | plattform | Aktionen: Status, Wartungsmodus, Anmeldung, Zwei-Faktor, Passwort Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). |

## `app/api/lib/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `adressen.php` | plattform | Adressen → Koordinaten auf dem eigenen Server (Plattformkern, genutzt von der CRM-Karte) Schlägt Straße + Hausnummer + PLZ/Ort in einem Adressverzeichnis aus OpenStreetMap nach (ODbL; erzeugt von … |
| `aktionen-liste.php` | plattform | ERZEUGT von `python3 werkzeuge/regeln.py erzeugen` aus regeln/aktionen/*.toml – nicht von Hand ändern. |
| `angebote.php` | angebot | Angebote, Kundenpreise, Sonderpreise, Datenmodell, gemeinsames Bearbeiten |
| `anmeldekonten.php` | plattform | Konten der zentralen Anmeldung (Keycloak, Realm „mitarbeiter“) aus der Verwaltung steuern – EIN Passwort für alles. |
| `auswertung.php` | verwaltung | Auswertung: Anmeldeorte der Kunden (ungefährer Ort aus der IP-Adresse, ort.php). |
| `benachrichtigung.php` | plattform | Benachrichtigungen an Mitarbeiter (E-Mail): welche Ereignisse an wen gehen, legt der Administrator fest. |
| `bereitschaft.php` | plattform | Bereitschaft für den Ernstfall (Oberfläche |
| `bestand-pdf.php` | bestand | Bestand als PDF (Verwaltung → Bestand → „PDF“) |
| `bestand.php` | bestand | Bestandsliste und Stammdaten |
| `diagnose.php` | plattform | Sicherheit für IT-Administratoren |
| `einkauf.php` | einkauf | Einkauf: Fehlmengen aus offenen Bestellwünschen gegenüber der zuletzt übernommenen Bestandsliste. |
| `einzelangebote.php` | angebot | Einzelangebote: ein Angebot für genau einen Kunden (Angebot bearbeiten → Einzelangebote). |
| `firewall.php` | plattform | Schutzzentrale: Firewall (Angriffsmuster), Sperrliste (von Hand, automatisch, Bedrohungsliste), Fallen für Angriffswerkzeuge, Fehlerbremse und Live-Verkehr. |
| `fracht.php` | angebot | Fracht: Mindestmenge für frachtfreie Lieferung, Frachtanteil je Staffel (unter X kg → Y € pro Sendung) und der Hinweis („Vermerk“) unter dem Angebot. |
| `geraete.php` | plattform | Vertraute Geräte: Nach einer erfolgreichen Anmeldung merkt sich der Browser eine zufällige Kennung (Cookie, nur für den Server lesbar); gespeichert wird beim Zugang nur deren Prüfsumme. |
| `herkunft.php` | plattform | Herkunftsprüfung im API-Einstieg (GR-109, ADR-003 §1) |
| `integritaet.php` | plattform | Dateiprüfung (wie ein Datei-Scanner gegen Schadcode): vergleicht die Programmdateien mit der Prüfliste der freigegebenen Fassung (integritaet-liste.php, beim Einspielen aus dem freigegebenen Commit erzeugt von … |
| `kern.php` | plattform | Antworten, Eingaben, Datenprüfung |
| `kunden.php` | verwaltung | Kundenstammdaten und Kunden-Sitzung |
| `kundenmail.php` | angebot | E-Mails an Kunden, Abmelden, Bestellwunsch-Vorlagen, Einmal-Links, Versand |
| `module-liste.php` | plattform | ERZEUGT von `python3 werkzeuge/regeln.py erzeugen` aus regeln/module.toml und regeln/wartung.toml – nicht von Hand ändern. |
| `module.php` | plattform | Modulzustand zur Laufzeit: wer darf welche Oberfläche nutzen (GR-102)? Grundlage ist ausschließlich die erzeugte Liste lib/module-liste.php (Modulregister regeln/module.toml und Entscheidungstabelle regeln/wartung.toml). |
| `notfall.php` | plattform | Notfallmodus (Oberfläche |
| `nutzer.php` | plattform | Mitarbeiter-Zugänge und Passwortregeln |
| `oidc.php` | plattform | Mitarbeiteranmeldung über Keycloak (ADR-003, GR-110) – Roadmap 7b, vorerst nur in CI und lokaler Testumgebung. |
| `passkey.php` | plattform | Passkeys (WebAuthn) für Mitarbeiter-Zugänge – ohne Fremdbibliothek. |
| `pdf-breiten.php` | plattform | Zeichenbreiten der PDF-Standardschriften Helvetica und Helvetica-Bold (WinAnsiEncoding, Byte 0–255, Tausendstel der Schriftgröße), aus den Adobe-Metriken. |
| `pdf.php` | plattform | Schlanker PDF-Erzeuger (ohne Fremdbibliothek) |
| `preisverlauf.php` | angebot | Preisverlauf (Wochenstände) |
| `protokoll.php` | plattform | Protokoll, Änderungstexte, Anmeldeversuche |
| `rechte.php` | plattform | Nutzerrechte: was eine Rolle bzw. ein einzelner Nutzer im Eingabebereich sehen und tun darf. |
| `sicherheit.php` | plattform | Sicherheitseinstellungen, Länder-/IP-Sperre, Zwei-Faktor, Sitzungsregister, Wartungsmodus |
| `sitzung.php` | plattform | Mitarbeiter-Sitzung, Rollen, Passwortbestätigung, CSRF |

## `app/api/module/angebot/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `import.php` | angebot | Importvertrag des Moduls Angebot – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md). - Preisverlauf: frühere Angebotslisten (.xlsx) als Wochen im Preisverlauf. |

## `app/api/module/bestand/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `import.php` | bestand | Importvertrag des Moduls Bestand – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md). |

## `app/api/module/controlling/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `controlling.php` | controlling | Modul Controlling · gemeinsame Grundlage aller Bereiche (Umsatzstatistik; geplant |
| `umsatz.php` | controlling | Controlling · Bereich Umsatzstatistik |

## `app/api/module/crm/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `crm.php` | crm | CRM · Vertrieb: Daten und Regeln des Moduls „crm“ (Oberfläche crm.intern, Aktionen in app/api/aktionen/crm.php) Kundenstammdaten (Nummer, Firma, Anschrift, Telefon, E-Mail, Vertreter, Gruppe, aktiv) gehören der … |

## `app/api/module/hr/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `export.php` | hr | Modul HR · Excel-Export für den Steuerberater: ein Blatt je Monat in Aufbau und Gestaltung der bisherigen Planungsdatei „Urlaub 2026“ (Legende, Monatstitel, Wochentage, Tageszahlen, Abteilungen senkrecht, Kürzel … |
| `import.php` | hr | Modul HR · Übernahme der bisherigen Planungsdatei („Urlaub 2026.xlsx“, ein Blatt je Monat). |
| `urlaub.php` | hr | Modul HR · Urlaubsverwaltung – Fachlogik (Daten, Feiertage, Urlaubskonto, Anträge, Monatsplan). |
| `zeiterfassung.php` | hr | Modul HR · Import „Abwesenheiten aus der Zeiterfassung“ (Abwesenheitsbericht, .xlsx) – Importvorlage für die Urlaubstage (Entscheidung des Inhabers, 23.10.2026). |

## `app/api/module/marketing/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `marketing.php` | marketing | Marketing · Redaktionsplan |

## `app/api/module/verwaltung/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `import.php` | verwaltung | Importvertrag der Verwaltung – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md). |
| `importzentrale.php` | verwaltung | Importzentrale (Verwaltung → Import, Roadmap 10b) – ein Ablauf für alle Importe |

## `app/assets/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `admin-artikelwahl.js` | angebot | Eingabebereich – Fenster „Artikel hinzufügen“ (gemeinsam für „Angebot bearbeiten“ und Einzelangebote) Links die VK-Gruppen (mit Anzahl), rechts die Artikel der gewählten Gruppe als Tabelle mit Häkchen, eingelagertem … |
| `admin-auswertung.js` | verwaltung | Wochenangebot – Eingabebereich, Auswertung Karte der Kunden-Anmeldungen: ungefährer Ort (aus der IP-Adresse) je Anmeldung, Liste, Filter nach Zeitraum und Kunde. |
| `admin-einzel.js` | angebot | Wochenangebot – Eingabebereich, Einzelangebote (Angebot je Kunde) Kunde über eine Suche wählen (Firma, Kundennummer, Ort, Ansprechpartner …). |
| `admin-import.css` | verwaltung | Eingabebereich – Importzentrale (Verwaltung → Import, admin-import.js) Nutzt die Farben und Bausteine von app.css/admin.css; hier nur die eigenen Teile. |
| `admin-import.js` | verwaltung | Wochenangebot – Eingabebereich, Importzentrale (Verwaltung → Import, Roadmap 10b) Ein Ablauf für alle Importe |
| `admin-rollen.js` | plattform | Wochenangebot – Eingabebereich, Verwaltung → Rollen und Rechte (nur Administratoren) Eigene Rollen anlegen, umbenennen, kopieren und löschen; je Rolle: welche Module sie öffnen darf (Modulzugang „<modul>.zugang“) und … |
| `admin-verwaltung.js` | verwaltung | Wochenangebot – Eingabebereich, Verwaltung Mitarbeiter, Bestellungen, Kunden, E-Mail, Protokoll. |
| `admin-werbung.js` | angebot | Eingabebereich – Fenster „Werbung schalten“ (Angebot bearbeiten, Knopf „Werbung“ in der Werkzeugleiste) Überschrift, optionaler Werbetext und bis zu 12 Artikel des gewählten Angebots (Reihenfolge, je Artikel ein … |
| `admin.css` | plattform | Eingabebereich – ergänzt app.css |
| `admin.js` | angebot | Wochenangebot – Eingabebereich Bearbeitet einen Entwurf auf dem Server (automatisch gespeichert). |
| `app.css` | angebot | Designsystem „Klar“: neutrale Flächen, ein Akzent (Bordeaux), Geist / Geist Mono (lokal eingebunden, SIL Open Font License, assets/fonts/LICENSE-Geist.txt – keine Verbindung zu fremden Servern) |
| `bestaetigt.js` | angebot | Rücksprungseite der Bestätigung im eigenen Fenster (admin/bestaetigt.html): meldet dem Eingabebereich, dass die erneute Anmeldung bei der STAFL-Anmeldung abgeschlossen ist, und schließt das Fenster. |
| `detailkarte.js` | plattform | STAFL-Plattform – Detailkarte (Straßen, Gebäude, Ortsnamen) vom eigenen Server Gemeinsame Kartenkomponente für die CRM-Karte und die Auswertung der Verwaltung. |
| `frontend.js` | angebot | Wochenangebot – öffentliches Frontend |
| `legal.css` | angebot | Gestaltung der Rechtsseiten (Kontakt, Impressum, Datenschutz): eigenes kleines Stylesheet ohne app.css, hell/dunkel nach Systemeinstellung. |
| `offer-core.js` | angebot | Wochenangebot – gemeinsamer Kern für Frontend und Eingabebereich - Excel-Leser (ohne externe Bibliothek) - Parser der Angebotsliste → editierbares Datenmodell - Anreicherung (Merkmale, Teilstück, Merklisten-Schlüssel … |
| `stock-core.js` | bestand | Bestand – Einlesen der WinAB-Bestandsliste („Partieliste … verfügbar“) Liest .xls (BIFF2–BIFF8, auch im OLE-Container) und .xlsx. |
| `theme.js` | plattform | Hell/Dunkel-Einstellung vor dem ersten Zeichnen anwenden (ohne Inline-Skript, wegen Content-Security-Policy) |
| `webapp.js` | angebot | Web-App: Offline-Speicher (sw.js) anmelden und Hinweis „Als App auf den Home-Bildschirm“. |

## `app/assets/karte/schrift/Noto Sans Italic/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `0-255.pbf` | plattform | – |
| `1024-1279.pbf` | plattform | – |
| `256-511.pbf` | plattform | – |
| `512-767.pbf` | plattform | – |
| `768-1023.pbf` | plattform | – |
| `7680-7935.pbf` | plattform | – |
| `8192-8447.pbf` | plattform | – |
| `8448-8703.pbf` | plattform | – |

## `app/assets/karte/schrift/Noto Sans Medium/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `0-255.pbf` | plattform | – |
| `1024-1279.pbf` | plattform | – |
| `256-511.pbf` | plattform | – |
| `512-767.pbf` | plattform | – |
| `768-1023.pbf` | plattform | – |
| `7680-7935.pbf` | plattform | – |
| `8192-8447.pbf` | plattform | – |
| `8448-8703.pbf` | plattform | – |

## `app/assets/karte/schrift/Noto Sans Regular/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `0-255.pbf` | plattform | – |
| `1024-1279.pbf` | plattform | – |
| `256-511.pbf` | plattform | – |
| `512-767.pbf` | plattform | – |
| `768-1023.pbf` | plattform | – |
| `7680-7935.pbf` | plattform | – |
| `8192-8447.pbf` | plattform | – |
| `8448-8703.pbf` | plattform | – |

## `app/assets/karte/sprite/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `LICENSE-tangrams.md` | plattform | – |

## `app/data/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `index.php` | plattform | Schutz des Datenordners: direkter Aufruf liefert 404 (Daten nur über api/storage.php). |

## `app/datenschutz/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `index.html` | angebot | Seite „Datenschutz · Standard-Fleisch“ |

## `app/impressum/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `index.html` | angebot | Seite „Impressum · Standard-Fleisch“ |

## `app/kontakt/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `index.html` | angebot | Seite „Kontakt · Standard-Fleisch“ |

## `app/module/controlling/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `controlling.css` | controlling | STAFL-Plattform · Controlling – Gestaltung „Liquid Glass“ wie Dashboard, HR, CRM und Marketing: warmer Grund mit drei weichen Farbflächen, Glasflächen, kein Rot im Hintergrund. |
| `controlling.js` | controlling | STAFL-Plattform · Controlling – Grundgerüst der Seite |
| `index.html` | controlling | Bereiche des Controllings: je Bereich ein Reiter und ein Inhalt (Skript des Bereichs, z. |
| `umsatz.js` | controlling | STAFL-Plattform · Controlling · Bereich Umsatzstatistik |

## `app/module/crm/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `crm.css` | crm | STAFL-Plattform · CRM · Vertrieb – Gestaltung wie Dashboard und HR („Liquid Glass“): heller Grund mit weichen Farbflächen, Glasflächen für Kopf, Karten und Tabellen. |
| `crm.js` | crm | STAFL-Plattform · CRM · Vertrieb Cockpit, Kunden, Wiedervorlagen (Anruf-Rhythmus), Pipeline, Karte und Auswertung – nach der Vertriebs-CRM-Musterdatei. |
| `index.html` | crm | Kundenblatt |

## `app/module/hr/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `hr.css` | hr | STAFL-Plattform · HR · Urlaub – Gestaltung wie das Dashboard („Liquid Glass“): heller Grund mit weichen Farbflächen, Glasflächen für Kopf und Karten. |
| `hr.js` | hr | STAFL-Plattform · HR · Urlaub Mitarbeiter: eigenes Urlaubskonto, Urlaubsantrag, eigene Einträge, Abwesenheitskalender (Kollegen nur „abwesend“). |
| `index.html` | hr | Mein Urlaub |
| `verwaltung-hr.css` | hr | STAFL-Plattform · HR im Eingabebereich der Verwaltung (Mitarbeiter-Dialog, Urlaubseinstellungen, Altbestand). |
| `verwaltung-hr.js` | hr | STAFL-Plattform · HR im Eingabebereich der Verwaltung - Verwaltung → Mitarbeiter |

## `app/module/marketing/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `index.html` | marketing | Beitrag |
| `marketing.css` | marketing | STAFL-Plattform · Marketing · Redaktionsplan – Gestaltung wie Dashboard, HR und CRM („Liquid Glass“): heller Grund mit weichen Farbflächen, Glasflächen für Kopf, Karten, Kalender und Board. |
| `marketing.js` | marketing | STAFL-Plattform · Marketing · Redaktionsplan Social-Media-Inhalte planen, produzieren, freigeben und veröffentlichen |

## `app/module/sicherheit/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `index.html` | sicherheit | Seite „STAFL-Plattform · Sicherheit“ |
| `sicherheit.css` | sicherheit | STAFL-Plattform · Sicherheit – „Leitstand“ (Entwurf des Inhabers 26.10.2026): dunkel ein Leitstand mit Graphit-Grund, Bordeaux- und Blaulicht, hell dieselbe Gliederung auf warmem Grau; folgt der Hell/Dunkel-Wahl am … |
| `sicherheit.js` | sicherheit | STAFL-Plattform · Sicherheit (Modul sicherheit, Oberfläche sicherheit.intern; docs/plattform/modul-sicherheit.md) Reiter |

## `dashboard/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `abgemeldet.html` | dashboard | Seite „STAFL-Plattform · Abgemeldet“ |
| `dashboard.css` | dashboard | STAFL-Plattform · Dashboard – Gestaltung „Liquid Glass“ (vom Inhaber freigegebener Entwurf) Ruhiger heller Grund mit drei weichen Farbflächen, Glasflächen für Kopfzeile und Kacheln. |
| `dashboard.js` | dashboard | STAFL-Plattform · Dashboard Kacheln kommen ausschließlich aus dem Modulregister (Aktion module_status, regeln/module.toml) – keine fest programmierte Liste. |
| `index.html` | dashboard | Seite „STAFL-Plattform · Dashboard“ |

## `deploy/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `adressen-laden.sh` | plattform | Adressverzeichnis für die CRM-Karte laden |
| `aktualisieren.sh` | plattform | Holt neue Versionen aus GitHub und spielt sie ein (läuft alle 2 Minuten per systemd-Timer). .env und daten/ werden nie verändert (außer der Statusdatei daten/sicherung.php der Datensicherung). |
| `altdateien.sh` | plattform | Alte Datendateien aufräumen |
| `bereitstellen.py` | plattform | Bereitstellung eines Stands |
| `datenbank-umschalten.sh` | plattform | Speicher umschalten: Dateien → SQLite (migrate) oder zurück (rollback), im Wartungsfenster durch den Betreiber. |
| `datenbank.py` | plattform | Offline migration/rollback and online SQLite backup. |
| `einrichten.sh` | plattform | Einmalig auf dem Server ausführen: richtet die automatische Aktualisierung ein. |
| `freigabe-einspielen.sh` | plattform | Release-Modus: spielt nur einen von Hand freigegebenen Commit ein (GitHub-Workflow „Release“), prüft danach die Erreichbarkeit wie ein Besucher und kehrt bei Fehlern automatisch zur Vorversion zurück. |
| `ip-freigabe-aus.php` | plattform | Offline emergency tool, also supports SQLite. |
| `ip-freigabe-aus.sh` | plattform | Notfall: IP-Freigabe und Ländersperre ausschalten (z. |
| `karte-laden.sh` | plattform | Detailkarte (Straßen, Gebäude, Ortsnamen) für CRM-Karte und Auswertung laden – OpenStreetMap-Daten als eine Datei auf dem eigenen Server (keine fremden Kartendienste beim Ansehen). |
| `notfall-aus.php` | plattform | Notfallmodus beenden (Server-Werkzeug zu deploy/notfall-aus.sh) – gleicher Ablauf wie notfall_ende() in app/api/lib/notfall.php, aber ohne Anmeldung |
| `notfall-aus.sh` | plattform | Notfallmodus beenden (Modul Sicherheit), wenn das in der Oberfläche nicht mehr geht – z. |
| `notzugang.sh` | plattform | Notzugang zum alten Eingabebereich (angebot-stafl.de/admin/ mit eigener Anmeldung) – nur wenn die zentrale Anmeldung (Keycloak) gestört ist. |
| `passwort-zuruecksetzen.php` | plattform | Wird von passwort-zuruecksetzen.sh im App-Container ausgeführt (nicht über das Web erreichbar). |
| `passwort-zuruecksetzen.sh` | plattform | Notfall: Passwort eines Nutzers zurücksetzen (z. |
| `release-modus-einrichten.sh` | plattform | Einmalig auf dem Server (als root) |
| `release-zurueck.sh` | plattform | Notfall: auf die Version vor dem letzten Release zurückgehen (Daten bleiben unverändert). sh /opt/wochenangebot/deploy/release-zurueck.sh Der zurückgenommene Stand wird nicht erneut automatisch eingespielt; ein neuer … |
| `sichern.sh` | plattform | Tägliche Datensicherung des Ordners daten/. |
| `sicherung-einrichten.sh` | plattform | Einmalig auf dem Server (als root): eigene Zeitsteuerung für die Datensicherung einrichten. sh /opt/wochenangebot/deploy/sicherung-einrichten.sh Danach läuft die Sicherung täglich um 02:30 Uhr unabhängig von der … |
| `sicherung-pruefen.php` | plattform | Prüft eine entpackte Datensicherung (Ersatz für sicherung-pruefen.py, falls kein Python vorhanden ist): jede Datendatei muss gültiges JSON enthalten. |
| `sicherung-pruefen.py` | plattform | Prüft eine entpackte Datensicherung: jede Datendatei muss gültiges JSON enthalten. |
| `speicher.sh` | plattform | Speicherbelegung des Servers anzeigen und gefahrlos Aufräumbares entfernen (Docker-Zwischenspeicher, ungenutzte Images). cd /opt/wochenangebot && sh deploy/speicher.sh # nur anzeigen – ändert nichts cd … |
| `testumgebung.sh` | plattform | Testumgebung test.<Domain> auf demselben Server – vollständig getrennt vom Echtbetrieb (eigener Ordner, eigener Container, nur Testdaten, keine E-Mails, Passwortschutz). sh deploy/testumgebung.sh einrichten einmalig |
| `wartung-aus.php` | plattform | Notfall: alle Wartungen beenden – Angebotsseite (Dokument „wartung“) und alle Bereiche (Dokument „module“). |
| `wartung-aus.sh` | plattform | Notfall: alle Wartungen beenden (Angebotsseite und alle Bereiche), z. |

## `deploy/anmeldung/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `LIESMICH.md` | plattform | Zentrale Anmeldung – Betriebskonfiguration |
| `apache-oidc.conf` | plattform | STAFL-Plattform – Keycloak-Hosts im Anwendungs-Container (ADR-003). |
| `app-abfrage.php` | plattform | Wird von deploy/anmeldung/konten.sh im App-Container ausgeführt (über die Standardeingabe, nicht über das Web). php -- postfach → Zugangsdaten des Postfachs der Anwendung als JSON (Eingabebereich oder .env), nur für … |
| `docker-compose.anmeldung.yml` | plattform | STAFL-Plattform – zentrale Anmeldung im Betrieb (ADR-003, Roadmap |
| `einrichten.sh` | plattform | Zentrale Anmeldung – Schritt 2 der Inbetriebnahme (docs/plattform/inbetriebnahme-anmeldung.md) |
| `konten.sh` | plattform | Zentrale Anmeldung – Konten in Keycloak über die Serverkonsole verwalten (ohne Browser und ohne SSH-Tunnel). |
| `pruefen.sh` | plattform | Prüft die vorbereitete Betriebskonfiguration der zentralen Anmeldung (deploy/anmeldung) – lokal mit Docker und in der CI. |
| `ruecksicherung-probe.sh` | plattform | Rücksicherung der Keycloak-Datenbank üben – ohne Eingriff in den Betrieb (Schritt 7 der Inbetriebnahme). |

## `deploy/anmeldung/theme/stafl/email/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `theme.properties` | plattform | – |

## `deploy/anmeldung/theme/stafl/email/html/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `executeActions.ftl` | plattform | STAFL-Plattform: E-Mail „Konto aktualisieren“ (Einladung aus der Verwaltung bzw. konten.sh einladen, Link zum Passwort-Festlegen) im Stil der Plattform-Mails (app/api/mail.php: mail_layout_einladung). |

## `deploy/anmeldung/theme/stafl/email/messages/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `messages_de.properties` | plattform | – |

## `deploy/anmeldung/theme/stafl/email/text/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `executeActions.ftl` | plattform | STAFL-Plattform: Textfassung der E-Mail „Konto aktualisieren“ (zur HTML-Fassung html/executeActions.ftl) |

## `deploy/anmeldung/theme/stafl/login/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `login-config-totp.ftl` | plattform | template: login-config-totp.ftl |
| `login-otp.ftl` | plattform | template: login-otp.ftl |
| `theme.properties` | plattform | – |

## `deploy/anmeldung/theme/stafl/login/messages/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `messages_de.properties` | plattform | – |

## `deploy/anmeldung/theme/stafl/login/resources/css/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `stafl.css` | plattform | STAFL-Plattform · Anmeldeseite (Keycloak) – Gestaltung „Liquid Glass“ Farben und Formen aus dashboard/dashboard.css und dem Eingabebereich (app/assets/admin.css, body.adm): ruhiger warmer Grund mit drei weichen … |

## `deploy/anmeldung/theme/stafl/login/resources/js/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `stafl-otp.js` | plattform | STAFL-Plattform – Einmalcode-Felder der Anmeldeseite (Felder mit data-stafl-otp |

## `deploy/image/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `Dockerfile` | plattform | STAFL-Plattform – Anwendungs-Image (Roadmap 7b-4, ADR-003) Grundlage für die spätere zentrale Anmeldung: das offizielle PHP-/Apache-Image plus das Apache-Modul mod_auth_openidc (OpenID-zertifiziert, aus den … |
| `pruefen.sh` | plattform | Prüft das Anwendungs-Image (deploy/image/Dockerfile) gegen das bisherige Grundimage – lokal mit Docker und in der CI. bash deploy/image/pruefen.sh # baut stafl-app:pruefung und vergleicht Erwartung: gleiche geladene … |

## `deploy/karte/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `adressen.py` | plattform | Adressverzeichnis für die CRM-Karte aus OpenStreetMap (ODbL) |
| `deutschland.geojson` | plattform | – |

## `deploy/testumgebung/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `apache-schutz.conf` | plattform | Testumgebung: ganze Seite nur mit Benutzername/Passwort (zusätzlich zu den Anmeldungen der Anwendung) |
| `docker-compose.yml` | plattform | Testumgebung (test.<Domain>) – wird von deploy/testumgebung.sh nach /opt/wochenangebot-test kopiert und dort gestartet. |

## `docs/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `app-api.md` | mobile | Schnittstelle für die App (iOS/Android) |
| `app-grundlagen.md` | mobile | Grundlage für eine Kunden- und Mitarbeiter-App |
| `architektur.md` | plattform | Architektur – was liegt wo |
| `bestand-wochenpreise.md` | bestand | Bestand: Wochenpreise und erwartete Zugänge |
| `bestell-api-v1.md` | angebot | Bestell-API, Antwortformat 1 |
| `bestell-mailversand.md` | angebot | Versandaufträge für Bestellwünsche |
| `dashboard-dns.md` | plattform | STAFL-Dashboard: DNS und Caddy-Vorbereitung |
| `datenbank.md` | plattform | SQLite-Datenablage (Schema 1) |
| `rechtliche-seiten.md` | angebot | Kontakt, Impressum und Datenschutz |
| `release-freigabe.md` | plattform | Release freigeben |
| `sicherheitspruefung-2026-10-17.md` | plattform | Sicherheitsprüfung vom 17.10.2026 |
| `testumgebung.md` | plattform | Testumgebung `test.<Domain>` |

## `docs/entwickler/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `01-schnellstart.md` | plattform | 1 · Schnellstart |
| `02-architektur.md` | plattform | 2 · Architektur |
| `03-server.md` | plattform | 3 · Server (PHP-API) |
| `04-anmeldung-rechte.md` | plattform | 4 · Anmeldung, Sitzungen, Rechte |
| `05-daten.md` | plattform | 5 · Daten und Speicher-Dokumente |
| `06-oberflaechen.md` | plattform | 6 · Oberflächen (Browser) |
| `07-tests.md` | plattform | 7 · Tests |
| `08-betrieb.md` | plattform | 8 · CI, Release und Betrieb |
| `09-anleitungen.md` | plattform | 9 · Anleitungen |
| `10-konventionen.md` | plattform | 10 · Konventionen |
| `README.md` | plattform | Entwickler-Dokumentation der STAFL-Plattform |

## `docs/entwickler/referenz/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `api.md` | plattform | Referenz: API-Aktionen |
| `dateien.md` | plattform | Referenz: Dateien |
| `daten.md` | plattform | Referenz: Speicher-Dokumente |
| `module.md` | plattform | Referenz: Module und Oberflächen |
| `rechte.md` | plattform | Referenz: Rechte |

## `docs/plattform/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `README.md` | plattform | STAFL-Plattform – Überblick |
| `adr-003-domains-anmeldung.md` | plattform | ADR-003: Domainstruktur und Mitarbeiteranmeldung |
| `bestandsaufnahme.md` | plattform | Bestandsaufnahme (Phase 0) – Stand 21.10.2026 |
| `inbetriebnahme-anmeldung.md` | plattform | Inbetriebnahme der zentralen Anmeldung (Keycloak) – Ablaufplan |
| `modul-sicherheit.md` | sicherheit | Modul Sicherheit (sicherheit.dashboard-stafl.de) |
| `multi-agent.md` | plattform | Entwicklung mit mehreren KI-Agenten |
| `roadmap.md` | plattform | Roadmap – priorisierte Pull Requests |
| `zielarchitektur.md` | plattform | Zielarchitektur der STAFL-Plattform |

## `docs/plattform/schnittstellen/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `import.md` | plattform | Schnittstelle: Importverträge und Importzentrale |

## `regeln/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `berechtigungen.toml` | plattform | Zuordnung der Mitarbeiterrechte zu Modulen. |
| `datenverantwortung.toml` | plattform | Datenverantwortung: welchem Modul gehört welches Speicher-Dokument (app/api/storage.php)? Regel GR-101 |
| `katalog.toml` | plattform | Katalog der verbindlichen Geschäfts- und Architekturregeln. |
| `module.toml` | plattform | Modulregister der STAFL-Plattform – einzige Quelle für Module, Oberflächen, Zuständigkeiten und Code-Pfade. |
| `wartung.toml` | plattform | Zustandsmodell je Oberfläche |

## `regeln/aktionen/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `LIESMICH.md` | plattform | Aktionsregister |
| `angebot.toml` | angebot | Aktionen des Moduls „angebot“ |
| `bestand.toml` | bestand | Aktionen des Moduls „bestand“ |
| `controlling.toml` | controlling | Aktionen des Moduls „controlling“: gemeinsamer Start und je Bereich eigene Aktionen controlling_<bereich>_… (heute Umsatzstatistik; geplant OP-Konten, Liquidität). |
| `crm.toml` | crm | Aktionen des Moduls „crm“ |
| `einkauf.toml` | einkauf | Aktionen des Moduls „einkauf“ |
| `hr.toml` | hr | Aktionen des Moduls „hr“ |
| `marketing.toml` | marketing | Aktionen des Moduls „marketing“ |
| `mobile.toml` | mobile | Aktionen des Moduls „mobile“ |
| `plattform.toml` | plattform | Aktionen des Moduls „plattform“ |
| `sicherheit.toml` | sicherheit | Aktionen des Moduls „sicherheit“ |
| `verwaltung.toml` | verwaltung | Aktionen des Moduls „verwaltung“ |

## `tests/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `README.md` | plattform | Automatische Tests |
| `run_e2e.py` | plattform | Startet für jede Testgruppe einen frischen PHP-Server mit Testdaten und führt die Ende-zu-Ende-Tests aus. python3 tests/run_e2e.py # alle Gruppen (parallel, WA_JOBS Gruppen gleichzeitig) python3 tests/run_e2e.py … |

## `tests/deploy/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `github_stub.py` | plattform | Minimaler Ersatz für die GitHub-API im Deploy-Test: liefert Release- und CI-Läufe aus einer Zustandsdatei. |
| `test_adressen_laden.sh` | plattform | Test von deploy/adressen-laden.sh – mit Platzhaltern für docker und curl, in einem Wegwerf-Ordner (lädt nichts herunter). |
| `test_altdateien.sh` | plattform | Test von deploy/altdateien.sh (Altdateien nach der Umschaltung auf SQLite) – echtes deploy/datenbank.py in einem Wegwerf-Ordner mit synthetischen Datensätzen, Platzhalter nur für die Sicherung (keine echten Daten, … |
| `test_anmeldung_einrichten.sh` | plattform | Test von deploy/anmeldung/einrichten.sh (Schritt 2 der Inbetriebnahme) – in einem Wegwerf-Ordner, ohne Docker. |
| `test_dashboard_domains.py` | plattform | Dashboard-Hosts: Modul-Hosts bleiben 503-Platzhalter bis zur Freigabe (GR-105); die Hosts der zentralen Anmeldung (ADR-003, Inbetriebnahme Schritt 6) führen nur zu Zielen, die es ausschließlich mit der … |
| `test_datenbank.py` | plattform | Real PHP/SQLite, independent SQL inspection, migration failure and restore tests. |
| `test_datenbank_umschalten.sh` | plattform | Test von deploy/datenbank-umschalten.sh – Vorprüfung vor Sicherung und Stopp, mit Platzhaltern für docker, sichern.sh und datenbank.py in einem Wegwerf-Ordner (keine echten Daten, kein Container). |
| `test_freigabe.sh` | plattform | Integrationstest des Release-Modus (deploy/freigabe-einspielen.sh) – komplett lokal: eigenes Git-„origin“, GitHub-API-Ersatz, PHP-Testserver als Live-Seite, echte Datensicherung. |
| `test_images.py` | plattform | Container-Images fest über Digest (Sicherheitsdurchsicht 26.10.2026, Befund 12): jedes fremde Image in den Compose-Dateien und im Dockerfile ist mit @sha256 festgelegt – ein Release holt so nie unbemerkt eine andere … |
| `test_karte_laden.sh` | plattform | Test von deploy/karte-laden.sh – mit Platzhaltern für docker und curl, in einem Wegwerf-Ordner (lädt nichts herunter). |
| `test_konten_pruefen.sh` | plattform | Test von „konten.sh pruefen“ (Anmeldeprobleme erkennen) – mit Platzhalter für kcadm und einer lokalen Zeitquelle, ohne Docker. |
| `test_notzugang.sh` | plattform | Test von deploy/notzugang.sh – mit Platzhalter für docker compose, in einem Wegwerf-Ordner. |
| `test_release_pruefen.sh` | plattform | Test der Release-Prüfungen (.github/scripts/release-pruefen.sh) mit einem Platzhalter für gh |
| `test_sichern.sh` | plattform | Test der Datensicherung (deploy/sichern.sh) in einem Wegwerf-Ordner mit Testdaten. |
| `test_speicher.sh` | plattform | Test von deploy/speicher.sh – mit Platzhalter für docker, in einem Wegwerf-Ordner. |
| `test_sqlite_http.sh` | plattform | Exercise real production PHP image and Apache, not the built-in test server. |
| `test_testumgebung.sh` | plattform | Test der Testumgebung-Verwaltung (deploy/testumgebung.sh) mit Platzhaltern für docker und git – ohne Server. |

## `tests/e2e/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `auth_helpers.py` | plattform | HTTP-Client und Zeitsteuerung ausschließlich für isolierte Testdaten/Sitzungen. |
| `kunden_hilfe.py` | plattform | HTTP-Client mit eigener Sitzung für API-Tests (IP über X-Forwarded-For, wie hinter dem eigenen Proxy). |
| `order_setup.py` | angebot | Gemeinsame Vorbereitung der Bestell-Testgruppen |
| `smtp_test.py` | plattform | Kleiner Test-Mailserver für die Ende-zu-Ende-Tests (nimmt Nachrichten an und hält sie im Speicher). |
| `test_admin_confirmation.py` | plattform | Sensible Aktionen, kontoweite Bestätigungsbremse und Dateisperren über echte HTTP-Anfragen. |
| `test_admin_confirmation_ui.py` | plattform | Abgelaufene Admin-Freigabe im Browser |
| `test_aktionsregister.py` | plattform | Aktionsregister (regeln/aktionen/*.toml → app/api/lib/aktionen-liste.php) wirkt im API-Einstieg für jede Aktion. |
| `test_angebote.py` | angebot | Mehrere Angebote: Kundenangebote mit eigenen Preisen, eigene Artikelliste je Angebot (Artikel hinzufügen wie im Einzelangebot, entfernen nur im gewählten Angebot, Umstellung „folgt dem Wochenangebot“ → eigene Liste), … |
| `test_angebotsliste.py` | angebot | Angebotsliste (Standardansicht der Angebotsseite) |
| `test_anmeldebremse.py` | plattform | Fehlversuchsbremse je Adresse (lib/protokoll.php), Abmelden mit CSRF und Bedrohungsliste ohne Nebenwirkung beim Lesen. - Eine erfolgreiche Anmeldung nimmt nur die Fehlversuche für denselben Namen zurück (eigene … |
| `test_anmeldeseite.py` | plattform | Testgruppe anmeldeseite |
| `test_app_api.py` | mobile | Schnittstelle für die App (docs/app-api.md) |
| `test_app_web.py` | mobile | App (mobile/) als Web-Build gegen den echten Testserver |
| `test_auswertung.py` | verwaltung | Auswertung: Karte der Kunden-Anmeldungen. |
| `test_auth_hardening.py` | plattform | Direkte HTTP-Regressionen |
| `test_benachrichtigung.py` | plattform | Benachrichtigungen an Mitarbeiter |
| `test_bestaetigung.py` | plattform | Sicherheit (Modul) → Einstellungen → Passwortbestätigung: je Aktion einstellbar, ob das Passwort verlangt wird; feste Aktionen (Zugänge, Rechte, Sicherheit, Postfach) immer mit Bestätigung; Gültigkeitsdauer … |
| `test_bestand_pdf.py` | bestand | Bestand: Marke je Partie (Spalte E der WinAB-Liste, Überschrift „Marke“ eine Spalte rechts davon), dezente MHD-Farben (hell/dunkel) und PDF ohne Preise, erfassten Bestand, Gesamt verfügbar und erwartete Zugänge. |
| `test_bestellung.py` | angebot | Bestellwunsch aus dem Portal |
| `test_controlling.py` | controlling | Controlling (Modul controlling, Oberfläche controlling.intern unter /module/controlling/) – erster Bereich Umsatzstatistik. |
| `test_crm.py` | crm | CRM · Vertrieb (Modul crm, Oberfläche crm.intern unter /module/crm/). |
| `test_dashboard.py` | dashboard | Mitarbeiter-Dashboard (dashboard/, Roadmap PR 6) |
| `test_design.py` | angebot | Gestaltung der Angebotsseite („Klar“ mit dem Design „Liquid Glass“: schwebende Glas-Kopfzeile, Kapseln, Liste als Glaskarte): lokale Schriften (keine fremden Server), Kopf, Filterleiste mit Aufklappmenüs (Desktop) bzw. |
| `test_editor_aux.py` | angebot | Testgruppe editor_aux |
| `test_einheit.py` | plattform | Einheitliches Erscheinungsbild aller Mitarbeiter-Oberflächen (Dashboard, Eingabebereich auf den Bereichs-Hosts Angebot, Verwaltung, Bestand, HR, CRM, Abmeldeseite, Hinweis „Kein Zugang“): je hell/dunkel und 1440/390 … |
| `test_einkauf.py` | einkauf | Einkauf: Fehlmengen aus offenen Bestellwünschen gegenüber dem Bestand, Rechte je Rolle (Ansehen für alle, Kundennamen und Melden ab Bearbeiter), E-Mail an die Empfänger „Einkaufsbedarf“, Status „gemeldet“, Oberfläche. |
| `test_einzelangebote.py` | angebot | Einzelangebote (Angebot bearbeiten → Einzelangebote) |
| `test_fehlerpruefung.py` | angebot | Regressionstests der Design- und Fehlerprüfung |
| `test_frontend.py` | angebot | search |
| `test_gemeinsam.py` | angebot | Mehrere Mitarbeiter bearbeiten den Entwurf gleichzeitig |
| `test_geo.py` | plattform | Testgruppe geo: Ländersperre im Modul Sicherheit (Einstellungen → Ländersperre, Dialog) – Länderliste nach Kontinenten, Schnellauswahl (Kontinente, EU, EWR, DACH, Nachbarn, NATO, G7, BRICS), Suche, … |
| `test_geo_ip.py` | plattform | Testgruppe geo_ip: IP-Suche der Ländersperre (Modul Sicherheit, Dialog Ländersperre) – IPv4/IPv6 einem Land zuordnen, Hinweise, nur für Administratoren. |
| `test_geraete.py` | plattform | Vertraute Geräte: Ein Browser, auf dem sich ein Zugang schon erfolgreich angemeldet hat, kommt auch während einer fremd ausgelösten Kontosperre mit dem richtigen Passwort durch (Mitarbeiter mit und ohne Zwei-Faktor, … |
| `test_herkunft.py` | plattform | Herkunftsprüfung im API-Einstieg (GR-109, lib/herkunft.php): nur Anfragen von der eigenen Seite. `Sec-Fetch-Site` same-site/cross-site → 403 (auch von Nachbar-Subdomains wie test.angebot-stafl.de); bei Anfragen außer … |
| `test_hist.py` | angebot | Testgruppe hist: Preisverlauf – Import alter Angebotslisten, Zeiträume, Datendialog. |
| `test_hr.py` | hr | HR · Urlaubsverwaltung (Modul hr, Oberfläche hr.intern unter /module/hr/). |
| `test_hr_uebersicht.py` | hr | HR · Urlaubsübersicht aller Mitarbeiter (Recht hr.uebersicht, Personalstelle hr.verwalten sieht sie auch). |
| `test_importzentrale.py` | verwaltung | Importzentrale (Verwaltung → Import, Roadmap 10b): eine Stelle für alle Importe mit einheitlichem Ablauf (Importart → Datei → Vorschau neu/geändert/entfällt/Fehler je Zeile → Übernahme → Ergebnis und Protokoll). |
| `test_integritaet.py` | plattform | Dateiprüfung (Sicherheit → Dateiprüfung) |
| `test_kunden.py` | verwaltung | Kunden: Stammdaten, Freischaltung von Angeboten, Kunden-Anmeldung auf der Angebotsseite. |
| `test_kunden_mail.py` | angebot | E-Mail an Kunden: Einladung mit Einmal-Link, Passwort-Link, Angebotslink, Wochenversand, Testmail. |
| `test_kundengruppen.py` | verwaltung | Stammdaten: Navigation (Artikel, Kunden, Kundengruppen), Kundengruppen per CSV (Windows-1252/UTF-8) importieren, bearbeiten, Rechte, Zuordnung im Kunden, Protokoll. |
| `test_kundenimport.py` | verwaltung | Stammdaten → Angebote mit Kundengruppen (Freischaltung über die Gruppe), Import der Kundenstammdaten aus der Warenwirtschaft (CSV, alle Spalten, Aktiv-Regel 18 Monate) und Passwort-Auswahl im Kunden-Dialog. |
| `test_legal_pages.py` | angebot | Öffentlich erreichbar, Navigation ohne JavaScript und mobile Darstellung. |
| `test_mail_intern.py` | plattform | Postfach für interne E-Mails (z. |
| `test_marketing.py` | marketing | Marketing · Redaktionsplan (Modul marketing, Oberfläche marketing.intern unter /module/marketing/). |
| `test_master.py` | verwaltung | Testgruppe master: Artikelstammdaten und Bezeichnungsregeln (Fleischart, Herkunft, Zustand, VK-Gruppe). |
| `test_modul_wartung.py` | plattform | Wartung je Oberfläche (GR-107) |
| `test_module_status.py` | plattform | Modulzustand zur Laufzeit (GR-102) |
| `test_modulverwaltung.py` | plattform | Modulverwaltung (Roadmap 5, GR-102) |
| `test_notfall.py` | sicherheit | Notfallmodus (Modul Sicherheit, lib/notfall.php, docs/plattform/modul-sicherheit.md). |
| `test_nutzer_anlegen.py` | plattform | Verwaltung → Nutzer anlegen |
| `test_oidc_dashboard.py` | plattform | Dashboard-Host (dashboard-stafl.de): nur Grundaktionen (lib/herkunft.php, host_nur_grundaktionen, GR-109). |
| `test_oidc_kern.py` | plattform | Zentrale Anmeldung – Verhalten der Anwendung ohne Keycloak (lib/oidc.php, GR-110). |
| `test_order_management.py` | angebot | Testgruppe order_management |
| `test_order_management_ui.py` | angebot | Artikelnummer als normale Tabellenzelle (Klasse „mono“ ist in app.css das runde Kategorie-Monogramm) |
| `test_order_outbox.py` | angebot | Testgruppe order_outbox: dauerhafte Versandaufträge für Bestellwunsch-Mails – Teilfehler, SMTP-Ausfall, Sperren, Neuversand. |
| `test_order_outbox_ui.py` | angebot | Testgruppe order_outbox_ui |
| `test_p0.py` | angebot | 1) leeres System ohne WA_INSTALLED → Ersteinrichtung erlaubt |
| `test_passkeys.py` | plattform | Passkeys (WebAuthn) für Mitarbeiter-Zugänge. |
| `test_passwortpruefung.py` | plattform | Datenleck-Prüfung der Passwörter („Pwned Passwords“, nachgebauter Dienst auf AUX_PORT): standardmäßig aus; eingeschaltet werden betroffene Passwörter beim Festlegen abgelehnt (Mitarbeiter, Kunden), bestehende bei der … |
| `test_protokoll.py` | plattform | Aufbewahrung des Aktivitätsprotokolls (lib/protokoll.php, PROTOKOLL_MONATE = 6; Inhaber 25.10.2026). |
| `test_rechte.py` | plattform | Nutzerrechte: Rechte je Rolle (einstellbar) und Ausnahmen je Nutzer (erlauben/verbieten). |
| `test_restposten.py` | angebot | Sonderposten (kurzes MHD, solange der Vorrat reicht), Ausblenden in jedem Angebot, eigene Artikelliste (Sonderposten nur für eigene Artikel), Kein-Bestand-Zeichen und Sonderposten-Mail je Angebot. |
| `test_revert.py` | angebot | sauberer Ausgangspunkt: einmal veröffentlichen |
| `test_rollen.py` | plattform | Rollen und Rechte: eigene Rollen (anlegen, umbenennen, kopieren, löschen), Modulzugang „<modul>.zugang“ je Rolle, mehrere Rollen je Mitarbeiter, Standardrollen unverändert, Durchsetzung auf dem Server (GR-103), … |
| `test_rollen_host.py` | plattform | Modulzugang je Host: der Testserver meldet sich wie bestand.dashboard-stafl.de (WA_OBERFLAECHE=bestand.intern). |
| `test_schutz.py` | plattform | Schutzzentrale (Verwaltung → Schutz) |
| `test_security.py` | plattform | Testgruppe security: Zwei-Faktor-Anmeldung, Wiederherstellungscodes, Sitzungen, IP-Freigabe und Content-Security-Policy. |
| `test_sicherheit_bereitschaft.py` | sicherheit | Bereitschaft im Modul Sicherheit (lib/bereitschaft.php, docs/plattform/modul-sicherheit.md §8). |
| `test_sicherheit_druck.py` | plattform | Sicherheit, Druck und Formatierung |
| `test_sicherheit_freigaben.py` | plattform | Freigegebene Sicherheitsänderungen |
| `test_sicherheit_it.py` | plattform | Sicherheit für IT-Administratoren |
| `test_sicherheit_modul.py` | sicherheit | Modul Sicherheit (Oberfläche sicherheit.intern unter /module/sicherheit/, docs/plattform/modul-sicherheit.md). |
| `test_sidenav.py` | angebot | Testgruppe sidenav: Navigation des Eingabebereichs, Sichtbarkeit je Rolle, Kopfzeile ohne Überlappung und Darstellung je Bildschirmbreite. |
| `test_sitzung_cookie.py` | plattform | Sitzungs-Cookie mit Präfix __Host- über HTTPS (GR-108, ADR-003 Befund B-1). |
| `test_stilllegung.py` | plattform | Alter Eingabebereich stillgelegt (WA_EIGENE_ANMELDUNG=aus, lib/oidc.php): auf dem Host ohne zentrale Anmeldung (angebot-stafl.de) gibt es keine Mitarbeiteranmeldung und keine Mitarbeiteraktionen mehr; die Kundenseite … |
| `test_stock.py` | bestand | Summen exakt (Dezimal) und kaufmännisch gerundet wie die Anzeige – Gleitkomma-Summen kippen sonst bei ,xx5 je nach Datum |
| `test_stock_overview.py` | bestand | Exakte Wochenpreise, separate erfasste Zugänge, Validierung, Rechte und Anzeige. |
| `test_storage.py` | plattform | Publication persists consistently; injected storage failures never report success. |
| `test_sys.py` | angebot | Setup |
| `test_testumgebung.py` | plattform | Testumgebung (WA_TESTUMGEBUNG=1) |
| `test_users.py` | plattform | Testgruppe users: Mitarbeiterzugänge – Rollen, serverseitige Rechte, Protokoll, Sperren und Zwei-Faktor-Pflicht je Nutzer. |
| `test_versand.py` | angebot | Wochenangebot an Kunden senden |
| `test_vertreter.py` | verwaltung | Stammdaten → Vertreter (Liste aus der Warenwirtschaft) und die Felder „Vertreter“ und „Vertreter 2“ in den Kunden |
| `test_vkgruppen.py` | verwaltung | Stammdaten → VK-Gruppen und Import der Artikelstammdaten (CSV-Export der Warenwirtschaft) |
| `test_wartung.py` | angebot | Wartungsmodus und erweiterte Übersicht im Eingabebereich. |
| `test_web_app.py` | angebot | Web-App (zum Home-Bildschirm) |
| `testdaten.py` | plattform | Erwartungswerte aus den anonymisierten Testdaten (tests/fixtures) – statt fest eingetragener Zahlen. |
| `umgebung.py` | plattform | Gemeinsame Pfade für die Ende-zu-Ende-Tests (gesetzt vom Testlauf tests/run_e2e.py). |

## `tests/oidc/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `Caddyfile` | plattform | Testumgebung „Anmeldung über Keycloak“ (nur CI und lokal, GR-111) – bildet die Produktion nach |
| `LIESMICH.md` | plattform | Anmeldung über Keycloak – Testumgebung (Roadmap 7b) |
| `apache.conf` | plattform | Testumgebung „Anmeldung über Keycloak“ (Roadmap 7b, nur CI und lokal – GR-111). |
| `kcadm-stueckweise.sh` | plattform | Test: kcadm wie über „docker compose exec“ – die Ausgabe kommt in kleinen Stücken. |
| `postfach.py` | plattform | Kleiner Test-Mailserver für die Keycloak-Prüfungen (nimmt Nachrichten an, hält sie im Speicher). |
| `test_oidc.py` | plattform | Anmeldung über Keycloak (Roadmap 7b, ADR-003, GR-108/GR-110) – Prüfungen gegen die Testumgebung aus umgebung.sh. |
| `umgebung.sh` | plattform | Testumgebung „Anmeldung über Keycloak“ (Roadmap 7b, ADR-003) – nur CI und lokal, nie auf dem Server (GR-111). bash tests/oidc/umgebung.sh start # PostgreSQL, Keycloak (Realm „mitarbeiter“), Caddy (TLS), Apache + … |

## `tests/regeln/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `test_regeln.py` | plattform | Tests für werkzeuge/regeln.py: das echte Regelwerk ist stimmig, und typische Verstöße werden erkannt. |

## `tests/unit/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `adressen.php` | plattform | Hilfsskript für tests/unit/test_adressen.py |
| `bestand_parser.test.js` | bestand | Unit-Test: Der Bestands-Parser der App (stock-core.js) liefert für die Test-Bestandsliste exakt dieselben Summen wie die unabhängige Referenzauswertung (tests/fixtures/bestand/master_stock.json). |
| `merge.test.js` | angebot | Unit-Test: Drei-Wege-Abgleich beim gemeinsamen Bearbeiten des Entwurfs (OfferCore.mergeModels). |
| `stock_prices.php` | bestand | Isolated calendar/history selection tests, no server or production storage. |
| `stock_prices.test.js` | bestand | Unit-Test: Preisvergleich und Wochenpreise der Bestandsliste (StockCore aus app/assets/stock-core.js). |
| `test_adressen.py` | plattform | Adressverzeichnis der CRM-Karte |
| `test_apt_vorrat.py` | plattform | Paketvorrat der CI (.github/scripts/apt_vorrat.py) mit nachgebautem apt-cache. python3 tests/unit/test_apt_vorrat.py Prüft: nur Pakete mit passender SHA-256 aus der (signierten) Paketliste werden übernommen; … |
| `test_ci_nachweis.py` | plattform | Nachweis „schon im Pull Request vollständig geprüft“ (.github/scripts/ci_nachweis.py) mit nachgebauter GitHub-API. python3 tests/unit/test_ci_nachweis.py Prüft |
| `test_doku.py` | plattform | Werkzeug der Entwickler-Dokumentation (werkzeuge/doku.py) |
| `test_run_e2e_teile.py` | plattform | Aufteilung der E2E-Testgruppen auf CI-Aufträge (tests/run_e2e.py |

## `werkzeuge/`

| Datei | Modul | Inhalt |
| --- | --- | --- |
| `asset_versionen.py` | plattform | Einbindungen der Skripte und Stylesheets in den HTML-Seiten unter app/ prüfen. |
| `doku.py` | plattform | Nachschlageteil der Entwickler-Dokumentation aus dem Code erzeugen und prüfen (nur Python-Standardbibliothek). python3 werkzeuge/doku.py erzeugen docs/entwickler/referenz/*.md neu schreiben python3 werkzeuge/doku.py … |
| `integritaet.py` | plattform | Prüfliste der Dateiprüfung (app/api/lib/integritaet-liste.php): prüfen, dass sie NICHT im Repository steht. |
| `karte_auszug.py` | plattform | Kleiner Ausschnitt aus einer Protomaps-Basiskarte (PMTiles, OpenStreetMap-Daten, ODbL) – für Testdaten und lokale Vorschau der Detailkarte. |
| `karte_bauen.py` | verwaltung | Baut die Landkarte für die Auswertung (app/assets/karte.json) aus Natural Earth (gemeinfrei), weitergegeben als TopoJSON im npm-Paket „world-atlas“ (ISC). |
| `karte_stil.mjs` | plattform | – |
| `lokal.py` | plattform | Lokaler Entwicklungsserver mit Testdaten – wie ein Testserver der E2E-Suite, aber zum Ausprobieren im Browser. python3 werkzeuge/lokal.py http://127.0.0.1:8080 mit Testdaten (tests/fixtures/data-seed) python3 … |
| `nielsen_gebiete.py` | plattform | Nielsen-Gebiete für die CRM-Karte (app/module/crm/nielsen.json) aus den Bundesländern von Natural Earth erzeugen. |
| `realm_produktion.py` | plattform | Realm „mitarbeiter“ für den Betrieb aus dem geprüften Test-Realm erzeugen (eine Quelle, kein Auseinanderlaufen). python3 werkzeuge/realm_produktion.py # schreibt deploy/anmeldung/realm-mitarbeiter.json python3 … |
| `regeln.py` | plattform | Regelwerk der STAFL-Plattform prüfen und Änderungsfolgen ermitteln (nur Python-Standardbibliothek). python3 werkzeuge/regeln.py pruefen Alle Prüfungen (CI); Ausgang 1 bei Fehlern python3 werkzeuge/regeln.py betroffen … |
| `testdaten_erzeugen.py` | plattform | Erzeugt die anonymisierten Testdaten unter tests/fixtures aus echten Originaldateien. |
