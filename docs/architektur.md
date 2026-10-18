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
| `lib/sitzung.php` | Mitarbeiter-Sitzung, Rollen (`require_auth`), Passwortbestätigung, CSRF |
| `lib/sicherheit.php` | Sicherheitseinstellungen, Länder-/IP-Sperre, Zwei-Faktor, Sitzungsregister, Wartungsmodus |
| `lib/protokoll.php` | Protokoll (`audit`), Änderungstexte, Anmeldeversuche |
| `lib/angebote.php` | Angebote, Kundenpreise (`variants`), Sonderpreise (`sale`), `offer_resolve`, Datenmodell `clean_model`, Entwurfsrevisionen |
| `lib/kunden.php` | Kundenstammdaten, Kunden-Sitzung |
| `lib/kundenmail.php` | E-Mails an Kunden (Vorlagen, Abmelden, Einmal-Links, Versand, Protokoll), Bestellwunsch-Vorlage |
| `lib/benachrichtigung.php` | Benachrichtigungen an Mitarbeiter: Ereignisse (`NOTIFY_EVENTS`), Einstellungen, Vormerken (`notify`, aus `audit()`), Versand nach der Antwort mit Bündelung |
| `lib/preisverlauf.php`, `lib/bestand.php` | Preisverlauf; Bestandsliste und Stammdaten |
| `orders.php`, `order_outbox.php` | Bestellverwaltung (API v1) und Versandaufträge |
| `mail.php`, `geo.php`, `storage.php` | SMTP-Client, Länderdatenbank, Speicherschicht |
| `aktionen/*.php` | Die Aktionen (`?action=…`) nach Fachbereich: `angebote`, `kundenportal`, `mail`, `kundenverwaltung`, `zugang`, `bestand`, `verwaltung`, `entwurf`, `preisverlauf` |

Aktionsdateien werden im globalen Gültigkeitsbereich eingebunden (`$action`, `$CFG`, … stehen zur Verfügung); jede Aktion
endet mit `respond()`/`fail()`. Bibliotheks- und Aktionsdateien sind nur über `index.php` nutzbar (Konstante `WA_API`).
Neue Schreibaktionen gehören in `$writeActions` (index.php), öffentliche Kundenaktionen zusätzlich in `$isPublic`
und ggf. `WARTUNG_GESPERRT`.

## Browser (`app/assets/`)

| Datei | Inhalt |
| --- | --- |
| `offer-core.js` | Gemeinsamer Kern: Excel-Leser, Angebotsparser, Vergleich (`diffOffers`), Abgleich (`mergeModels`), Sonderpreise |
| `stock-core.js` | Bestandsliste lesen (WinAB .xls/.xlsx) |
| `frontend.js` + `app.css` | Angebotsseite: Filter, Merkliste, Kunden-Login, Bestellwunsch, „Meine Bestellwünsche“, Wartungsseite |
| `admin.js` + `admin.css` | Eingabebereich: Anmeldung, Entwurf bearbeiten, gemeinsames Bearbeiten, Angebote, Veröffentlichen, Preisverlauf, Bestand, Sonderposten, Stammdaten |
| `admin-verwaltung.js` | Eingabebereich, Verwaltung: Nutzer, Bestellungen, Kunden, E-Mail, Protokoll, Sicherheit (nutzt `window.WA` aus `admin.js`) |

Kein Build-Schritt. Nach Änderungen an `app/assets/` die Versionsnummern setzen: `python3 werkzeuge/asset_versionen.py --setzen`.

## Tests

- `tests/run_e2e.py` startet je Testgruppe einen frischen PHP-Server mit Testdaten (`tests/fixtures/`), parallel mit
  eigenen Ports (`WA_JOBS`). Tests holen Adressen aus `tests/e2e/umgebung.py`; Hilfen: `kunden_hilfe.Client`,
  `auth_helpers`, `wait_text()`, `until()`, `shot()`, Test-Mailserver `smtp_test.TestSmtp`.
- `tests/unit/*.test.js` (Node), `tests/deploy/*` (Sicherung, Release-Modus, Release-Prüfungen, Datenbank, Testumgebung).
- CI (`.github/workflows/ci.yml`): Syntax, Versionsnummern, Ports, Secrets, Abhängigkeiten, E2E in beiden Speicherarten.
