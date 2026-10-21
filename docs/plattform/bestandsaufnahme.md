# Bestandsaufnahme (Phase 0) – Stand 21.10.2026

Geprüft am Repository und – nur lesend, von außen – an den öffentlichen Adressen. Kein Serverzugang, keine Änderung
an Produktion, DNS oder Daten.

## GitHub

| Punkt | Befund |
| --- | --- |
| `main` | `9ffa8f5` (Merge von PR #62) – identisch mit dem Übergabestand |
| Offene Pull Requests | keine |
| Branches | 63, überwiegend erledigte `feature/*` – Aufräumen empfohlen (nur durch den Inhaber) |
| Letzte Freigabe | Tag `release-20261021-095201` → `9ffa8f5` |
| Sichtbarkeit | öffentlich (siehe Risiken) |

## Produktion (von außen geprüft)

| Adresse | Antwort | Bedeutung |
| --- | --- | --- |
| `https://dashboard-stafl.de`, `https://crm.dashboard-stafl.de` | 503 „in Vorbereitung“, `no-store`, `noindex` | Caddy-Stand aus PR #62 ist eingespielt |
| `https://angebot-stafl.de/api/index.php?action=app_info` | 200, `wartung: null`, `testumgebung: false` | Angebotsportal läuft normal, Wartung aus |
| `https://angebot-stafl.de/admin/` | 200 | heutiger Eingabebereich |
| `https://test.angebot-stafl.de` | 401 | Testumgebung mit Passwortschutz |

**Nicht von außen prüfbar:** ob SQLite auf dem Server aktiv ist (Marker `daten/.sqlite-active`) und welcher Commit genau
läuft. Bitte bei Gelegenheit auf dem Server prüfen: `ls -la daten/.sqlite-active` und `git -C /opt/… rev-parse HEAD`.

## Architektur heute

- **Laufzeit:** Docker Compose mit `php:8.3-apache` (Ordner `app/` nur lesend eingebunden, Daten in `daten/`) und Caddy
  (HTTPS, Sicherheitsheader, CSP, Fallenpfade). Kein Build-Schritt, keine Fremdbibliotheken im Server-Code.
- **Server-Code:** ein Einstieg `app/api/index.php` (RPC über `?action=`, 115 Aktionen in `aktionen/*.php`, `orders.php`,
  `order_outbox.php`), Bibliotheken in `app/api/lib/`. Zentrale Listen im Einstieg: Schreibaktionen, öffentliche
  Aktionen, `WARTUNG_GESPERRT`.
- **Oberflächen:** Kundenseite (`index.html`, `frontend.js`), Eingabebereich `/admin/` (`admin.js` 3.806 Zeilen,
  `admin-verwaltung.js` 1.919, `admin-einzel.js`, `admin-schutz.js`, `admin-auswertung.js`), App in `mobile/` (Expo).
- **Daten:** Dokumentenspeicher `app/api/storage.php` – JSON-Dateien oder SQLite-Tabelle `documents` (Schema 1,
  Umschaltung bewusst durch den Betreiber, `docs/datenbank.md`). 50 Dokumente, jetzt mit Eigentümer in
  `regeln/datenverantwortung.toml`. Sperren über `with_lock`, bei SQLite mit Transaktionen.
- **Sicherheit (vorhanden, wird wiederverwendet):** Mitarbeiter-Sitzungen mit CSRF, Rollen + Rechtekatalog `PERMS` mit
  Ausnahmen je Nutzer, Zwei-Faktor (App) und Passkeys (eigene WebAuthn-Prüfung), vertraute Geräte,
  Passwortbestätigung je Aktion, IP-/Ländersperre, Firewall/Fallen, Datenleck-Prüfung, Dateiprüfung, Protokoll.
  Kunden haben eigene Zugänge und Sitzungen (getrennt vom Eingabebereich).
- **Wartung heute:** ein globaler Schalter (Dokument `wartung`) sperrt nur Kundenaktionen mit 503; Mitarbeiter arbeiten
  weiter. Das ist genau „Angebot · Kunden-Frontend in Wartung“ im neuen Modell.

## Tests, CI, Release

- **E2E:** 58 Gruppen, frischer PHP-Server je Gruppe mit synthetischen Daten, beide Speicherarten. Lokal am 21.10.2026
  auf diesem Branch: Dateien **2.546/2.546** bestanden (Gruppe `app_web` übersprungen, braucht App-Build).
- **CI:** statische Prüfungen (Syntax, Caddy-Parser, Dashboard-Platzhalter, Versionsnummern, Prüfliste, actionlint),
  Sicherheitsprüfungen (gitleaks über den ganzen Verlauf, Trivy), Betrieb (Datenbankmigration, Sicherung,
  Release-Modus mit Healthcheck/Rückfall, Testumgebung), E2E-Matrix Dateien/SQLite.
- **Release:** grüne CI auf `main` → Release-Lauf wartet auf Freigabe in der Umgebung `produktion` → Tag → Server
  spielt per Timer ein (`deploy/freigabe-einspielen.sh`: Prüfung, Healthcheck, automatischer Rückfall).
- **Testumgebung:** `test.angebot-stafl.de` → Container `app-test` (synthetische Daten, Apache-Passwort,
  E-Mails ins Testpostfach).
- **Sicherung:** lokaler Timer (`deploy/sichern.sh`, bei SQLite über die Backup-API) + Hostinger-VPS-Backups.

## Befunde für den Plattformumbau

| Befund | Folge |
| --- | --- |
| Alle Fachfunktionen (Bestand, Stammdaten, Kunden, Einkauf, Nutzer, Sicherheit) liegen in einem Eingabebereich | Module werden schrittweise herausgelöst; bis dahin ist `angebot.eingabe` ihre Oberfläche |
| `admin.js`, `admin-verwaltung.js` und die Listen in `index.php` sind Sammelstellen | Hauptursache für Konflikte paralleler Agenten → neue Module registrieren Aktionen und Oberflächen selbst (PR 2) |
| Querzugriffe auf fremde Dokumente (z. B. Bestand schreibt Stammdaten, Kundenportal schreibt Kunden) | als „Altbestand“ erfasst und erlaubt; neue Querzugriffe lehnt die CI ab (GR-101) |
| Rechte-Schlüssel sind in gespeicherten Rollen enthalten | nicht umbenennen; neue Rechte mit Modulpräfix |
| Dokumentenspeicher ohne Relationen | genügt für das Angebot; für gemeinsame Stammdaten mehrerer Module → PostgreSQL ([zielarchitektur.md](zielarchitektur.md#datenbankstrategie)) |
| Kein Composer, kein Build-Schritt | bewusste Stärke (kleine Angriffsfläche); neue Abhängigkeiten nur mit Begründung |

## Risiken (dokumentiert, nicht behoben)

- **Öffentliches Repository:** Code und Architektur interner Module (Einkauf, QS, Bestand) werden öffentlich lesbar.
  Sicherheit darf nie davon abhängen; dennoch vor dem Bau interner Module über ein privates Repository entscheiden
  (Kosten: GitHub-Actions-Minuten). Geheimnisse und echte Daten bleiben ausgeschlossen (gitleaks im ganzen Verlauf).
- **Keine externe Sicherung** (auf Wunsch des Betreibers zurückgestellt): VPS-Totalausfall bzw. Kontoverlust bei Hostinger
  träfe Live-Daten, lokale Sicherungen und VPS-Backups gleichzeitig. Ein Wiederherstellungstest am Produktionssystem
  steht laut `docs/datenbank.md` noch aus.
- **HSTS mit `includeSubDomains` auf angebot-stafl.de** läuft probeweise mit 1 Tag; vor Verlängerung prüfen, dass jede
  künftige Subdomain HTTPS kann.
