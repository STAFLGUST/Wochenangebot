# Zielarchitektur der STAFL-Plattform

Festlegungen stehen maschinenlesbar in `regeln/` – hier stehen Begründung, Zusammenhang und Entscheidungen.
Status: **Konzept** (umgesetzt ist bisher nur das Regelwerk mit Prüfwerkzeug). Offene Punkte: [roadmap.md](roadmap.md#offene-entscheidungen).

## 1. Grundsatz: modularer Monolith

Ein Anwendungscontainer, ein gemeinsamer API-Einstieg, gemeinsame Dienste (Anmeldung, Rechte, Wartung, Speicher,
Protokoll, E-Mail) – Fachmodule mit klaren Grenzen darin. Bewertet gegen den vorhandenen Code: passt sehr gut, weil
Einstieg, Sitzungen, Rechte und Speicherschicht bereits zentral und gut getestet sind. Microservices würden Anmeldung,
Transaktionen und Betrieb auf dem einen VPS vervielfachen, ohne fachlichen Gewinn.

**Modul** = Eintrag in `regeln/module.toml`: ID, Kachel, Oberflächen (je mit Entwicklungsstand, Freigabe, sperrbar),
Abhängigkeiten, Code-Pfade, Agent, Testgruppen. Der Startumfang sind die 8 Kacheln; ein neues Modul ist ein neuer
Eintrag – das Dashboard liest das Register, es gibt keine fest programmierte Liste.

| Modul | Rolle | Oberflächen |
| --- | --- | --- |
| angebot | produktiv | Kunden-Frontend `angebot-stafl.de` (extern) · Mitarbeiter-Eingabe (intern) |
| bestand, crm, rewe, einkauf | Fachmodule | je `<id>.dashboard-stafl.de` |
| qs | nur technische Grundlage | intern `qs.dashboard-stafl.de` · extern QS-Portal (Domain offen) |
| import | eigene Kachel, **Teil der Verwaltung** | Kachel → `verwaltung.dashboard-stafl.de/import/`; keine eigene Implementierung (CI prüft) |
| verwaltung | Stammdaten, Benutzer/Rechte (Oberfläche), Module & Wartung | `verwaltung.…/`, `/import/`, `/system/` (nie sperrbar) |
| dashboard | Einstieg, keine Kachel | `dashboard-stafl.de` (nie sperrbar) |
| plattform | Kern, keine Kachel | – |
| mobile | App, keine Kachel | nutzt die API wie die Website |

## 2. Code-Struktur

**Entscheidung ADR-1:** `app/` bleibt Docroot; Module entstehen *darin*, nicht unter `apps/` + `packages/`.

```text
app/                         Docroot (nur lesend eingebunden, Prüfliste der Dateiprüfung)
├── index.html, assets/       Angebot · Kunden-Frontend (unverändert)
├── admin/ → eingabe/         Angebot · Mitarbeiter (Phase 7)
├── dashboard/                Dashboard-Oberfläche (heute noch unter /dashboard/ außerhalb von app/, nicht ausgeliefert)
├── module/<id>/              Oberflächen der Fachmodule (neu)
└── api/
    ├── index.php             gemeinsamer Einstieg: Anmeldung, Rechte, Wartung, CSRF, Protokoll
    ├── lib/                  Plattformkern + heutige Fachbibliotheken (ziehen schrittweise um)
    ├── aktionen/             heutige Aktionen
    └── module/<id>/          Server-Code je Fachmodul (neu): aktionen.php, lib.php, vertrag.php
regeln/  werkzeuge/  tests/  deploy/  docs/
```

Begründung: Die vorgeschlagene `apps/`/`packages/`-Struktur stammt aus JavaScript-Monorepos mit Build-Schritt. Hier
würde sie Docker-Einbindung, Prüfliste, Release-Skripte und Rückfall gleichzeitig ändern (Big-Bang-Risiko), ohne die
Modulgrenzen besser zu machen. Die Grenzen sichert das Register (Pfade je Modul) plus CI. Bestehende Dateien ziehen nur
um, wenn ein Modul ohnehin daran arbeitet.

## 3. Domains und Routing

| Host | Ziel | Heute |
| --- | --- | --- |
| `angebot-stafl.de` | Kunden-Frontend + `/api/` | produktiv |
| `angebot-stafl.de/admin/` | heutige Mitarbeiter-Eingabe; Ziel laut ADR-003: `angebot.dashboard-stafl.de` (alte Adresse leitet weiter) | produktiv |
| `dashboard-stafl.de` | Dashboard + Anmeldung | 503-Platzhalter |
| `<modul>.dashboard-stafl.de` | Modul-Oberfläche `app/module/<id>/` + `/api/` | 503-Platzhalter |
| `test.dashboard-stafl.de` | nicht als Testumgebung nutzen (ADR-003); Integration später auf eigener Testdomain | 503-Platzhalter |
| `login.dashboard-stafl.de` | Keycloak (ADR-003) | DNS fehlt |
| `angebot.dashboard-stafl.de` | Angebot · Mitarbeiter-Eingabe (ADR-003) | DNS fehlt |
| `test.angebot-stafl.de` | bestehende Testumgebung | produktiv (401) |

- Caddy schaltet einen Host erst frei, wenn **alle** seine Oberflächen eine Freigabe haben (GR-105, CI prüft gegen das
  Register). Freigegeben wird per Release, nicht per Klick.
- Alle Hosts gehen an denselben Container; der Server ermittelt Modul und Oberfläche aus dem Host über das Register,
  nicht aus einem Header. `angebot-stafl.de` liefert nie `/module/*` oder `/dashboard/*` aus (Caddy 404 – zusätzlich
  zur Prüfung im Server).
- Externe Oberflächen liegen nie unter `dashboard-stafl.de` (CI prüft, GR-104).

## 4. Anmeldung und Single Sign-on

Ausführliche Sicherheitsbewertung und Empfehlung: **[ADR-003](adr-003-domains-anmeldung.md)** (Entscheidungsvorlage,
angenommen am 21.10.2026, noch nicht umgesetzt). Kurzfassung:

- Getrennte Subdomains je Anwendung, Mitarbeiter-Eingabe des Angebots unter `angebot.dashboard-stafl.de`;
  die Kundendomain `angebot-stafl.de` enthält danach keine Mitarbeitersitzung mehr.
- OpenID Connect mit Keycloak als Identitätsanbieter auf eigenem Host `login.dashboard-stafl.de`; jede Anwendung ist ein
  eigener Client mit eigener, hostgebundener `__Host-`-Sitzung – **kein** gemeinsames Cookie für alle Subdomains.
- Rechte je Modul und Funktion prüft weiterhin unser Server bei jeder Aktion (GR-103).
- Kunden behalten ihre Zugänge unverändert; das QS-Portal erhält eine eigene Nutzergruppe (GR-104).
- Eigene registrierbare Testdomain mittelfristig; bis dahin läuft die neue Anmeldung nur in der CI (GR-111).

## 5. Datenarchitektur

- **Ein Eigentümer je Datum** (`regeln/datenverantwortung.toml`, GR-101). Andere Module lesen/schreiben über Funktionen
  des Eigentümers (`app/api/module/<id>/vertrag.php`), nie direkt in fremde Strukturen. Die CI erkennt neue
  Querzugriffe im Code; heutige sind als „Altbestand“ vermerkt und werden beim Umzug ersetzt.
- **Zentrale Stammdaten** (Artikel, Kunden, Lieferanten, Gruppen, Einheiten, Warengruppen) gehören der Verwaltung.
  CRM pflegt Ansprechpartner, Aktivitäten, Vorgänge (Entscheidung E-1).
- **Historie (GR-106):** abgeschlossene Vorgänge speichern einen Schnappschuss der damals gültigen Stammdaten
  (heute schon: Bestellwünsche, Versionen, Preisverlauf). Neue Module übernehmen das Muster; Stammdaten bekommen
  zusätzlich eine Änderungsversion, damit Schnappschüsse nachvollziehbar sind.
- **Schutzklassen** je Dokument (öffentlich/intern/vertraulich/geheim) – Grundlage für Exportregeln, Protokoll und
  später Rechte auf Datenbankebene.

### Datenbankstrategie

| Speicher | Eignung |
| --- | --- |
| Dateien (heute aktiv, vermutlich) | einfach, aber keine Transaktionen über Dokumente |
| SQLite-Dokumente (vorbereitet, `docs/datenbank.md`) | Transaktionen, konsistente Sicherung; ein Schreiber zur Zeit – reicht für das Angebot |
| **PostgreSQL (Ziel für gemeinsame Daten)** | gleichzeitige Schreiber, Fremdschlüssel/Constraints für Stammdaten, Schema und Datenbankrolle je Modul (GR-101 auch in der Datenbank), `pg_dump`/Point-in-Time-Sicherung |

Migrationspfad (jeder Schritt einzeln freigegeben, mit Rückweg):
1. Optional jetzt: SQLite aktivieren (fertig vorbereitet, Werkzeug mit Rückweg) – Entscheidung E-3.
2. Phase 8: PostgreSQL-Container nur in CI und Testumgebung; PHP-Image mit `pdo_pgsql` (eigenes Image statt
   `php:8.3-apache` – ändert Release und Prüfliste, eigener PR). `storage.php` erhält einen dritten Treiber mit
   derselben Tabelle `documents` (name, payload `jsonb`, mtime) – das Angebot läuft unverändert weiter.
3. Neue Modul-Daten (Stammdaten normalisiert, Bestand, Einkauf, CRM, QS) entstehen relational in Schemas je Modul;
   Migrationen versioniert unter `deploy/migrationen/`, in CI vorwärts und rückwärts getestet.
4. Produktive Umstellung nur nach geprüfter Sicherung **und** Wiederherstellungstest, im Wartungsfenster, mit Freigabe.

Keine automatische produktive Umstellung, keine acht Datenbanken.

## 6. Modulzustand und Wartung

Drei getrennte Eigenschaften je **Oberfläche**: Entwicklungsstand (Code, per PR), Freigabe (Administrator, protokolliert),
Betrieb (normal/Wartung, auch geplant). Wer zugreifen darf, entscheidet ausschließlich die Entscheidungstabelle in
`regeln/wartung.toml`; die CI prüft Vollständigkeit, Invarianten (z. B. „Wartung beenden macht nichts produktiv“) und
die Beispiele aus dem Auftrag als Vertragstests.

**Umgesetzt (Roadmap PR 3):** erzeugte Tabelle `app/api/lib/module-liste.php`, Auswertung `lib/module.php`, Lese-Aktion
`module_status`; Vertragstest: PHP und Prüfwerkzeug entscheiden alle Kombinationen gleich. Heute ist nur der bisherige
Wartungsmodus als Betrieb von `angebot.kunden` angebunden.

**Umgesetzt (Roadmap PR 4):** Wartung je Oberfläche für die Mitarbeiter-Eingabe (Dokument `module`, Grund, Hinweis,
geplanter Beginn, Verlauf, Protokoll, Passwortbestätigung), Durchsetzung im API-Einstieg, Sperrbildschirm,
Notfallwerkzeug `deploy/wartung-aus.sh`. Freigaben und Tester zur Laufzeit: Modulverwaltung (Modul Sicherheit → System → Module und Freigaben, Roadmap 5) – nur innerhalb des Entwicklungsstands im Code, Produktivbereiche und Verwaltung nur über ein Release.

Umsetzung (Phase 5):
- Laufzeitzustand im Dokument `module` (Freigabe, Wartung mit Beginn/Ende, Grund, Hinweis, Tester); Startwerte aus dem
  Register. Die Tabelle wird als erzeugte PHP-Datei ausgeliefert (Muster wie `aktionen-liste.php`), nicht nachprogrammiert.
- Jede Aktion ist genau einer Oberfläche zugeordnet; der Einstieg prüft Zustand → Anmeldung → Recht → CSRF, bevor die
  Aktion läuft. Wartung: 503, `Retry-After`, `Cache-Control: no-store`; Schreibaktionen auch für offene Sitzungen gesperrt;
  Importe/Hintergrundläufe pausieren; E-Mails bleiben in der Warteschlange.
- Getrennt je Oberfläche, z. B. Angebot: Kunden aktiv, Eingabe in Wartung; QS: Portal aktiv, intern in Wartung.
- Schutz vor Aussperrung: Dashboard und die Sicherheitszentrale mit dem Reiter System (bis 27.10.2026 Verwaltung → System)
  sind nicht sperrbar (CI prüft), Administratoren erreichen
  produktive Oberflächen auch in Wartung, Notfallskript auf dem Server analog `deploy/ip-freigabe-aus.sh`.
- Protokoll je Änderung (wer, wann, Modul, Oberfläche, alt, neu, Grund, geplante Dauer), Passwortbestätigung.
- Der heutige Wartungsmodus wird zu „angebot.kunden in Wartung“ – gleiches Verhalten, gleiche Tests (`e2e:wartung`).

## 7. API-Konzept

- Weiter RPC über `?action=` (bestehende Clients, App mit `apiVersion`), aber **Registrierung je Modul**: jede
  `app/api/module/<id>/aktionen.php` liefert eine Tabelle Aktion → Oberfläche, Recht, schreibend, öffentlich. Der Einstieg
  setzt Prüfungen einheitlich durch – keine verstreuten Listen mehr. **Umgesetzt** als `regeln/aktionen/<modul>.toml` →
  `app/api/lib/aktionen-liste.php`; die CI prüft, dass jede Aktion genau einem Modul und einer Oberfläche gehört.
  Noch offen: Durchsetzung „Aktion nur auf ihrem Host“ (GR-109), sobald es mehrere Hosts gibt.
- Modulübergreifend nur über `vertrag.php` des Eigentümers (PHP-Funktionen mit festen Ein-/Ausgaben). Änderungen nur
  erweitern; Vertragstests je Funktion im Eigentümer-Modul. Beschreibung der Verträge unter `docs/plattform/schnittstellen/`.
- Externe Schnittstellen (Bestell-API v1, App-API) bleiben versioniert wie heute.

## 8. Sicherheit (Querschnitt)

Serverseitige Prüfung jeder Aktion (GR-103), objektbezogene Prüfung im Eigentümer-Modul (z. B. Kunde sieht nur eigene
Angebote, Lieferant nur eigene Dokumente), CSRF, CSP ohne Inline-Skripte, Schutzklassen je Dokument, keine internen Daten
an öffentliche Endpunkte (GR-001/002/008), Uploads/Importe nur mit Prüfung beim Daten-Eigentümer, Protokoll, Geheimnisse
nur in `.env`, gitleaks und Trivy in der CI. Neue Fremdabhängigkeiten nur mit Begründung im PR.

## Entscheidungen (ADR)

| Nr. | Entscheidung | Status | Alternative |
| --- | --- | --- | --- |
| ADR-1 | `app/` bleibt Docroot, Module unter `app/module/` und `app/api/module/` | vorgeschlagen | `apps/`+`packages/` (Big-Bang-Risiko) |
| ADR-2 | Regelwerk als TOML (Python-Standardbibliothek), Laufzeit-Daten daraus erzeugt | **umgesetzt** | YAML (bräuchte Zusatzpaket in CI und PHP) |
| ADR-3 | Subdomains je Anwendung, OIDC (Keycloak), hostgebundene Sitzungen, Testdomain mittelfristig – [ADR-003](adr-003-domains-anmeldung.md) | **angenommen 21.10.2026, nicht umgesetzt** | Unterverzeichnisse (ein Origin, keine Isolation im Browser) |
| ADR-4 | PostgreSQL als Ziel für gemeinsame Daten, Dokumente zunächst unverändert | vorgeschlagen | nur SQLite (ein Schreiber, keine Rollen je Modul) |
| ADR-5 | Zugriff je Oberfläche nur über die Entscheidungstabelle | **umgesetzt (Spezifikation)** | Logik je Modul |
| ADR-6 | Kein CODEOWNERS vorerst | vorgeschlagen | siehe [multi-agent.md](multi-agent.md) |
