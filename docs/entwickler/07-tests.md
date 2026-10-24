# 7 · Tests

Wie man in diesem Repository testet und neue Tests schreibt. Die Liste aller Testgruppen mit ihrem Inhalt steht in
[`tests/README.md`](../../tests/README.md) und wird hier nicht wiederholt. Verbindlich sind die Regeln in
[`AGENTS.md`](../../AGENTS.md) (Tests, Definition of Done, „Schnell arbeiten, ohne Qualität zu verlieren“).

Grundsatz: Alle Tests laufen gegen **Testkopien mit anonymisierten Testdaten** aus `tests/fixtures/` – nie gegen den
Server, nie mit echten Daten (GR-007). Keine Erfolgsmeldung ohne tatsächlich ausgeführte Tests.

## 7.1 Testarten und Orte

| Art | Ort | Aufruf | Braucht |
| --- | --- | --- | --- |
| Ende-zu-Ende (E2E) | `tests/e2e/test_<gruppe>.py`, Starter `tests/run_e2e.py` | `python3 tests/run_e2e.py [gruppe …]` | PHP 8.3, Python, Playwright-Chromium |
| Unit (JavaScript) | `tests/unit/*.test.js` | `node tests/unit/<datei>.test.js` | Node.js |
| Unit (PHP) | `tests/unit/stock_prices.php` | `php tests/unit/stock_prices.php` | PHP 8.3 |
| Unit (CI-Werkzeuge) | `tests/unit/test_run_e2e_teile.py`, `test_ci_nachweis.py`, `test_apt_vorrat.py` | `python3 tests/unit/<datei>.py` | Python |
| Regelwerk | `werkzeuge/regeln.py`, `tests/regeln/test_regeln.py` | `python3 werkzeuge/regeln.py pruefen` und `python3 tests/regeln/test_regeln.py` | Python (nur Standardbibliothek) |
| Betrieb/Deploy | `tests/deploy/` | `sh tests/deploy/<datei>.sh` bzw. `python3 tests/deploy/<datei>.py` | Shell, Python, teils Docker |
| Keycloak-Anmeldung | `tests/oidc/` | `bash tests/oidc/umgebung.sh start` … `stop` | Apache, mod_auth_openidc, PostgreSQL, Java 21 |
| App (`mobile/`) | `mobile/` | `cd mobile && npm ci && npm run pruefen` | Node.js – steht derzeit **nicht** in `ci.yml` |

### Ende-zu-Ende-Tests (`tests/run_e2e.py`)

Eine **Gruppe** ist eine Testdatei `tests/e2e/test_<gruppe>.py` mit einem Eintrag in `SUITES`. Für jede Gruppe baut
`run_e2e.py` einen eigenen, frischen Testserver:

1. **App-Kopie:** `app/` wird nach `tests/.arbeit/app-<gruppe>/` kopiert. Darauf läuft
   `deploy/bereitstellen.py` (`verzeichnis()`) wie beim Einspielen auf dem Server: Versionsnummern `?v=…` setzen und die
   Prüfliste der Dateiprüfung erzeugen.
2. **Zusatz-Oberflächen** (`ZUSATZ`): Oberflächen außerhalb von `app/` werden nur für ihre Gruppe in die Kopie
   eingeblendet, z. B. `dashboard/` für die Gruppen `dashboard` und `rollen`.
3. **Testzustand des Modulregisters** (`REGISTER_TEST`): einzelne Gruppen stellen in *ihrer Kopie* von
   `app/api/lib/module-liste.php` geplante Module auf einen anderen Entwicklungsstand (derzeit `modulverwaltung`).
   Das Register im Code bleibt unverändert.
4. **Testdaten:** der Datenordner der Kopie wird durch `tests/fixtures/<seed>/` ersetzt (`data-seed` oder
   `data-seed-clean` für die Ersteinrichtung). Ist der dritte Wert des Eintrags `True`, legt der Starter vorab einen
   Administrator mit dem Testpasswort `ADMIN_PW` aus `run_e2e.py` an.
5. **Speicherart:** mit `WA_TEST_STORAGE=sqlite` werden die Testdaten mit `deploy/datenbank.py migrate … --offline`
   in SQLite übernommen (unter Windows mit einem eigenen, vereinfachten Weg – prüft nicht die Linux-Migration).
6. **PHP-Server:** `php -S 127.0.0.1:<port>` im Ordner der Kopie, mit eigener Sitzungsablage
   (`tests/.arbeit/sessions-<gruppe>/`). Ausgabe des Servers: `tests/.arbeit/php-<gruppe>.log`.
   Achtung: der eingebaute PHP-Server wertet kein `.htaccess` aus. Apache-Verhalten prüfen `tests/deploy/test_sqlite_http.sh`
   und `deploy/image/pruefen.sh` bzw. `deploy/anmeldung/pruefen.sh` mit dem echten Image.
7. **Testskript:** läuft mit `TZ=Europe/Berlin` und diesen Variablen: `WA_BASE` (Adresse des Testservers),
   `WA_AUX_PORT` (Hilfsserver, z. B. nachgebaute externe Dienste), `WA_SMTP_PORT`, `WA_SMTP_PORT2` (Test-Mailserver),
   `UDATA` (Datenordner der Kopie), `WA_SESSION_DIR`, `WA_WORK`. Zeitlimit je Gruppe: 900 Sekunden.
8. **Auswertung:** bestanden nur, wenn Exit-Code 0 **und** die letzte Zeile der Form `x/y passed` mit `x = y > 0`
   ausgegeben wurde. Volle Ausgabe: `tests/.arbeit/test-<gruppe>.log`.

**`SUITES`-Eintrag:** Tupel `(port, seed, admin[, umgebung])`.

- `port` wird nicht mehr ausgewertet (Überbleibsel); die Ports vergibt `ports()` je Arbeitsplatz.
- `umgebung` (optional) sind zusätzliche Umgebungsvariablen **für den PHP-Server**, z. B. `MAIL_SMTP_*` (Test-Mailserver),
  `WA_TESTUMGEBUNG`, `WA_OIDC`, `WA_OBERFLAECHE`, `WA_EIGENE_ANMELDUNG`. `MAIL_SMTP_PORT` und `WA_URL` ersetzt der Starter
  durch die Werte des Arbeitsplatzes, `{AUX}` durch den Hilfsport. `MAIL_*`, `WA_URL` und `DOMAIN` aus der eigenen
  Shell werden nie an den Testserver weitergereicht.
- Gruppen mit gleicher Vorbereitung teilen sich Einträge (`SUITES['versand'] = SUITES['kunden_mail']`).
- `OPTIONAL`: Gruppen, die einen vorherigen Build brauchen (`app_web` braucht `mobile/dist-web`). Fehlt er, überspringt
  der volle Lauf die Gruppe mit Hinweis.

**Steuerung über Umgebungsvariablen:**

| Variable | Wirkung | Standard |
| --- | --- | --- |
| `WA_JOBS` | Gruppen gleichzeitig; `1` zur Fehlersuche | `min(4, max(2, CPU-Kerne))` |
| `WA_PORT_BASE` | erster Port; Arbeitsplatz *n* nutzt `Basis + 10·n` bis `+3` (Web, Hilfsserver, Mail 1, Mail 2) | `9100` |
| `WA_TEST_STORAGE=sqlite` | Testdaten in SQLite statt Dateien | Dateien |
| `WA_TEIL=k/n` | nur Teil *k* von *n* (Aufteilung nach `GEWICHT`, siehe unten) | alle Gruppen |
| `WA_RETRY=0` | fehlgeschlagene Gruppen nicht wiederholen | Wiederholung an |
| `WA_SHOTS` | Ordner für Bildschirmfotos | `tests/.ergebnisse/` |

**`GEWICHT`:** geschätzte Laufzeit je Gruppe in Sekunden (Median aus CI-Protokollen). Bestimmt nur die
Startreihenfolge (lange zuerst) und die Aufteilung mit `WA_TEIL` – nie das Ergebnis. Fehlt ein Wert, zählt
`GEWICHT_STANDARD` (15 s); `tests/unit/test_run_e2e_teile.py` verlangt aber für jede nicht optionale Gruppe einen
Eintrag. Lokal nachstellen, was ein CI-Teil ausführt: `WA_TEIL=2/3 python3 tests/run_e2e.py` (erste Zeile nennt die Gruppen).

**Arbeitsordner:**

- `tests/.arbeit/` – App-Kopien, Sitzungen, Protokolle (`test-<gruppe>.log`, `php-<gruppe>.log`,
  `test-<gruppe>-fehlversuch.log`). Nie zwei Testläufe gleichzeitig im selben Arbeitsordner; parallele Agenten arbeiten
  je in ihrem Worktree und mit eigenem `WA_PORT_BASE`.
- `tests/.ergebnisse/` – Bildschirmfotos der Oberflächentests. In der CI bei Fehlern als Artefakt
  `e2e-ergebnisse-<speicherart>-teil<k>` (7 Tage).

### Hilfsmodule in `tests/e2e/`

| Modul | Zweck |
| --- | --- |
| `umgebung.py` | einzige Quelle für Adressen und Pfade: `BASE`, `SMTP_PORT`, `SMTP_PORT2`, `AUX_PORT`, `SH` (Bildschirmfotos), `FIX`, `WORK`, `XL44` (Test-Angebotsliste); Speicherzugriff unabhängig von der Speicherart (`storage_raw`, `storage_write`, `storage_docs`, `storage_sqlite`, `storage_lock`); Warten ohne feste Zeiten (`wait_text`, `until`); `shot()` für Bildschirmfotos |
| `kunden_hilfe.py` | `Client` – HTTP-Client mit eigener Cookie-Sitzung für API-Tests. `call(aktion, daten)` liefert `(status, json)` (mit `raw=True` zusätzlich den Text), übernimmt das CSRF-Token aus Antworten und setzt `X-Forwarded-For` auf die IP des Clients (Standard `198.51.100.1`); zusätzliche Kopfzeilen über `client.headers`. Außerdem `B` (= `BASE`) |
| `auth_helpers.py` | eigener `Client` mit `login()` und `expire()`; `expire_session()` setzt eine Passwortbestätigung in der Sitzungsablage zurück (ohne Testendpunkt in der Anwendung); Nutzerdaten lesen/ändern |
| `smtp_test.py` | `TestSmtp(port, …)` – Test-Mailserver im Speicher (EHLO, optional STARTTLS/TLS, AUTH, `messages`); Empfänger `abgelehnt@…` werden mit 550 abgewiesen |
| `testdaten.py` | Erwartungswerte aus den Fixtures berechnen (`angebot()`, `artikel()`, `preis()`, `de()` für deutsches Zahlenformat) – nie Preise oder Mengen fest eintragen |
| `order_setup.py` | gemeinsame Vorbereitung der Bestellgruppen (Kunde mit Zugang, veröffentlichtes Angebot, Test-Mailserver) |

### Unit-, Regelwerk- und Deploy-Tests

- **`tests/unit/`:** reine Logik ohne Server – Bestands-Parser, Abgleich beim gemeinsamen Bearbeiten, Bestandswochen und
  Preisvergleich (JavaScript und PHP), Aufteilung der E2E-Gruppen, Nachweis „schon im Pull Request geprüft“ (mit
  nachgebauter GitHub-API), Paketvorrat der CI.
- **`tests/regeln/test_regeln.py`:** prüft `werkzeuge/regeln.py`. Das echte Regelwerk muss stimmig sein; Negativtests
  bauen je ein kleines künstliches Projekt in einem Temp-Ordner und verändern genau eine Stelle.
- **`tests/deploy/`:** Betriebsskripte ohne Server, meist mit Platzhaltern für `docker`, `git`, `gh` bzw. Keycloak
  (`kcadm`) in einem Wegwerf-Ordner. Beispiele: `test_freigabe.sh` (Release-Modus mit eigenem Git-„origin“,
  GitHub-API-Ersatz `github_stub.py` und PHP-Testserver als Live-Seite), `test_sichern.sh`, `test_release_pruefen.sh`,
  `test_testumgebung.sh`, `test_notzugang.sh`, `test_konten_pruefen.sh`, `test_anmeldung_einrichten.sh`,
  `test_datenbank.py` (Migration, Parallelzugriffe, Wiederherstellung), `test_dashboard_domains.py`.
  `test_sqlite_http.sh` braucht Docker (echtes `php:8.3-apache`).

### Keycloak Ende-zu-Ende (`tests/oidc/`)

Bildet die Mitarbeiteranmeldung vollständig nach – **nur in der CI und lokal, nie auf dem Server** (GR-111). Details:
[`tests/oidc/LIESMICH.md`](../../tests/oidc/LIESMICH.md).

```sh
bash tests/oidc/umgebung.sh start && python3 tests/oidc/test_oidc.py; bash tests/oidc/umgebung.sh stop
```

- `umgebung.sh start` startet PostgreSQL, Keycloak (Realm `mitarbeiter`), Caddy mit Test-TLS und Apache mit
  mod_auth_openidc; Keycloak und Caddy werden mit fester Version und Prüfsumme geladen (`umgebung.sh laden` nur
  herunterladen). Geheimnisse entstehen bei jedem Start neu (`tests/.arbeit/oidc/geheim.env`).
- Hosts `*.stafl.test` trägt das Skript in `/etc/hosts` ein (mit `sudo`, wenn nicht als root).
- **Feste Ports:** 8443 (steht in den Rücksprungadressen des Realms, nicht änderbar), 8081, 8180/9180 (Keycloak),
  8280 (Apache), 5433 (PostgreSQL). Nicht parallel zu einem zweiten Keycloak-Lauf auf derselben Maschine starten.
- Nach dem Realm-Import führt die Umgebung `deploy/anmeldung/konten.sh realm-aktualisieren` aus – die CI prüft also
  denselben Weg wie der Betrieb. Keycloak-Updates: Version und Prüfsumme in `umgebung.sh` und
  `deploy/anmeldung/docker-compose.anmeldung.yml` gemeinsam ändern.
- Die E2E-Gruppe `oidc_kern` prüft nur den Anwendungsteil ohne Keycloak (`WA_OIDC=1`).

## 7.2 Lokale Vorbereitung

| Was | Woher | Hinweis |
| --- | --- | --- |
| Python 3.12 | System | CI: `actions/setup-python` mit `3.12` |
| Python-Pakete | `pip install -r tests/requirements.txt` | fest versioniert: `playwright`, `openpyxl`, `cryptography` |
| Chromium | `python -m playwright install chromium` | CI: `--with-deps chromium` (inkl. Systempakete) |
| PHP 8.3 (CLI) | System | CI installiert PHP nicht eigens, sondern nutzt das PHP 8.3 des Runners `ubuntu-24.04` |
| Node.js | System | für `tests/unit/*.js` und die Syntaxprüfung |
| Docker | System | nur für einzelne Deploy-Prüfungen und Image-Prüfungen |
| Für `tests/oidc/` | `apache2 libapache2-mod-auth-openidc libapache2-mod-php8.3 postgresql`, Java 21 | wie `.github/scripts/testumgebung.sh oidc` |

**PHP-Erweiterungen:** Die Anwendung prüft in `app/api/lib/diagnose.php` auf `sodium` (verschlüsseltes
Postfach-Passwort), `openssl` (TLS zum Mailserver), `pdo_sqlite` (Speicherart SQLite) sowie `mbstring`, `intl` und
`opcache`. Für die E2E-Suite in beiden Speicherarten mindestens `pdo_sqlite`, `sodium`, `openssl` und `mbstring`
bereithalten. Python braucht das Modul `sqlite3` (Standardbibliothek).

**Windows:** Der Starter läuft, einige ältere Gruppen brauchen aber `fcntl`, Unix-Prozessbefehle oder Linux-Dateirechte.
Maßgeblich ist der Lauf unter Linux (CI).

## 7.3 Einen neuen Test schreiben

### Aufbau einer Testdatei

Jede Gruppe ist ein eigenständiges Python-Skript mit demselben Gerüst:

```python
"""Was die Gruppe prüft (ein Satz, Bezug auf Regel GR-xxx, falls zutreffend)."""
import sys
from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'   # Testpasswort des vorab angelegten Administrators
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


# … Prüfungen …

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
```

- Jede Prüfung läuft über `check(name, bedingung[, info])` und schreibt `PASS …` oder `FAIL …`. Bei Fehlern im dritten
  Wert das Ist-Ergebnis mitgeben – der Starter zeigt `FAIL`-Zeilen im Gesamtprotokoll.
- Die Schlusszeile `x/y passed` und der Exit-Code sind Pflicht; ohne sie gilt die Gruppe als fehlgeschlagen.
- Eine Ausnahme bricht die Gruppe ab und wird als `Traceback` gemeldet. Prüfungen der Form `check(…, True)` nach einem
  `wait_for_selector` sind nur indirekt – lieber die Bedingung selbst prüfen.
- Namen der Prüfungen sagen, was erwartet wird („Leser: Einkaufspreis weder in der Antwort noch in der Tabelle“).

### API-Tests mit `Client`

```python
A = Client('198.51.100.2')                       # eigene Sitzung, eigene IP
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
code, r = A.call('stock')
check('Leser ohne Recht: 403', code == 403, r)
```

- Je Rolle bzw. Person einen eigenen `Client` mit eigener IP verwenden (Dokumentationsbereich `198.51.100.x`, siehe
  vorhandene Gruppen). Für sehr viele Anfragen hintereinander eine interne Adresse (`10.x`) nehmen – die Fehlerbremse der
  Firewall sperrt solche Adressen nie (Beispiel: `test_aktionsregister.py`).
- Immer auch Rechte und Fehlerfälle prüfen: ohne Anmeldung (401), ohne Recht (403), ohne CSRF, falsche Methode/Art,
  veralteter Stand (409), ungültige Eingabe (422). Neues Verhalten ohne diese Fälle gilt nicht als getestet.
- Gespeicherten Zustand direkt prüfen nur über `umgebung.storage_raw()`/`storage_docs()` – so funktioniert der Test
  in beiden Speicherarten. Zeitablauf simulieren mit `storage_write()` bzw. `auth_helpers.expire_session()`.
- Mails: `smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')` und im `SUITES`-Eintrag die `MAIL_SMTP_*`-Werte
  (Vorlage: Eintrag `bestellung`).

### Oberflächentests mit Playwright

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch()
    fehler = []
    for breite in (1280, 390):
        pg = br.new_page(viewport={'width': breite, 'height': 800}, is_mobile=breite < 500)
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        # … bedienen, auf den erwarteten Zustand warten, prüfen …
        check(f'{breite}: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth') <= breite)
        pg.screenshot(path=SH + f'/meine-gruppe-{breite}.png')
        pg.close()
    check('keine JavaScript-Fehler', not fehler, fehler[:3])
    br.close()
```

- Desktop **und** 390 px prüfen (Definition of Done), bei neuen Farben auch dunkel (`color_scheme='dark'`).
- JavaScript-Fehler über `page.on('pageerror', …)` sammeln und am Ende prüfen.
- Bildschirmfotos nach `SH` schreiben (eindeutige Dateinamen je Gruppe); sie dienen der Sichtprüfung.

### Regeln für stabile Tests

- **Keine festen Wartezeiten.** Nie `wait_for_timeout` vor einem `check`, sondern auf den erwarteten Zustand warten:
  `wait_for_selector`, `wait_for_function`, `umgebung.wait_text()` oder `umgebung.until()` (Python-seitig).
- **Ports und Adressen nur über `umgebung.py`** (`BASE`, `SMTP_PORT`, `SMTP_PORT2`, `AUX_PORT`). Die CI bricht ab, wenn
  in `tests/e2e/` außerhalb von `umgebung.py` eine Adresse `127.0.0.1:<Port>` steht.
- **Hintergrundabgleich:** Der Eingabebereich zeigt bei beendeter Sitzung jederzeit die Anmeldemaske. Nach Abmelden,
  Sitzungsablauf oder Sperre darf ein Test nicht annehmen, dass die Seite bedienbar bleibt – neu laden bzw. neu anmelden.
- **Keine fest eingetragenen Geschäftswerte:** Preise, Mengen und Summen aus `testdaten.py` berechnen.
- **Nur Testdaten:** neue Fixtures nur anonymisiert unter `tests/fixtures/` (Erzeugung: `werkzeuge/testdaten_erzeugen.py`),
  Test-E-Mail-Adressen unter `example.org`. Testwerte, die wie Geheimnisse aussehen, meldet gitleaks.
- **Unabhängigkeit:** eine Gruppe darf sich nur auf ihren eigenen frischen Server verlassen, nicht auf andere Gruppen
  oder eine Reihenfolge.

### Neue Gruppe registrieren

Alles im selben PR, sonst lehnt die CI ab:

1. `tests/e2e/test_<gruppe>.py` anlegen (Name: Kleinbuchstaben, Ziffern, `_`).
2. In `tests/run_e2e.py` einen `SUITES`-Eintrag ergänzen (`'<gruppe>': (8790, 'data-seed', True)` bzw.
   `SUITES['<gruppe>'] = …`) – nur diese beiden Schreibweisen erkennt `werkzeuge/regeln.py`.
3. Einen Wert in `GEWICHT` eintragen (anfangs geschätzt, mit Kommentar „noch ohne CI-Median“); später aus den
   CI-Zeilen „[gruppe] … bestanden in N s“ erneuern.
4. Die Gruppe genau einem Modul zuordnen: `testgruppen = [...]` in [`regeln/module.toml`](../../regeln/module.toml).
   `regeln.py pruefen` meldet Gruppen ohne Modul und Modulverweise auf fehlende Gruppen.
5. Prüft die Gruppe eine Geschäftsregel, sie in `regeln/katalog.toml` bei der Regel unter `tests` nennen
   (`"e2e:<gruppe>"`; außerdem erlaubt: `"datei:<pfad>"`, `"ci:<Name eines CI-Schritts>"`).
6. Zeile in der Gruppentabelle von [`tests/README.md`](../../tests/README.md) ergänzen (Prüfungen, Schwerpunkt).
7. Danach `python3 werkzeuge/regeln.py pruefen`, `python3 tests/regeln/test_regeln.py` und
   `python3 tests/unit/test_run_e2e_teile.py` ausführen.

Eine Aufteilung der CI auf mehr oder weniger Teile ändert `ci.yml` an zwei Stellen (`teil: [1, 2, 3]` und Nenner in
`WA_TEIL`); `test_run_e2e_teile.py` prüft, dass beides zusammenpasst.

### Wackel-Erkennung

Schlagen höchstens drei Gruppen fehl, wiederholt `run_e2e.py` sie einmal allein (ohne Parallellast). Vorher wird das
Protokoll nach `tests/.arbeit/test-<gruppe>-fehlversuch.log` kopiert. Besteht die Gruppe dann, bleibt der Lauf grün,
meldet sie aber als **wackelig** (`::warning::` in GitHub). Solche Gruppen zeitnah stabilisieren – meist eine feste
Wartezeit oder eine Annahme über die Reihenfolge. Aufspüren unter mehr Last und ohne Wiederholung:

```sh
WA_RETRY=0 WA_JOBS=5 python3 tests/run_e2e.py
```

Bei mehr als drei fehlgeschlagenen Gruppen gibt es keine Wiederholung; der Lauf ist rot.

## 7.4 Welche Tests vor einem PR laufen müssen

1. **Änderungsfolgen ermitteln:**

   ```sh
   python3 werkzeuge/regeln.py betroffen --basis origin/main
   ```

   Ausgabe: betroffene Module, abhängige Module, berührte Daten, koordinationspflichtige Bereiche, Regeln, die
   E2E-Gruppen („Tests während der Entwicklung“) und weitere Prüfungen. Die Ausgabe gehört in den PR-Text.
   Sind Plattformkern oder koordinationspflichtige Bereiche berührt, ist der PR erst mit grüner CI „bereit zum Mergen“.
2. **Während der Entwicklung** nur diese Gruppen: `python3 tests/run_e2e.py gruppe1 gruppe2`.
3. **Vor dem PR** dieselben Gruppen in beiden Speicherarten:

   ```sh
   python3 tests/run_e2e.py gruppe1 gruppe2
   WA_TEST_STORAGE=sqlite python3 tests/run_e2e.py gruppe1 gruppe2
   ```

4. **Immer:** `python3 werkzeuge/regeln.py pruefen`, `python3 werkzeuge/doku.py pruefen`,
   `python3 werkzeuge/asset_versionen.py`, `python3 werkzeuge/integritaet.py`; bei Änderungen an Skripten unter `deploy/` die passenden `tests/deploy/`-Tests.
5. Die **volle** E2E-Suite in beiden Speicherarten und die Keycloak-Prüfung laufen in der CI (Pflicht-Checks). Lokal die
   volle Suite nur zur Fehlersuche oder wenn die CI nicht verfügbar ist. Im PR stehen beide Ergebnisse (lokal und CI),
   Vorlage: [`.github/pull_request_template.md`](../../.github/pull_request_template.md).

### Was die CI macht

Bei jedem Pull Request und jedem Commit auf `main` läuft `.github/workflows/ci.yml` (Aufträge im Einzelnen:
[08 – CI, Release und Betrieb](08-betrieb.md)). Kurz:

- **Statische Prüfungen:** Syntax (PHP, JavaScript, Python, Shell), Caddy-Konfiguration, Regelwerk, Entwickler-Doku, Einbindungen,
  Prüfliste, keine festen Ports in Tests, Unit-Tests, Workflows.
- **Sicherheitsprüfungen:** gitleaks über den Verlauf, Trivy für Testabhängigkeiten und Images.
- **Ende-zu-Ende-Tests:** 2 Speicherarten × 3 Teile, je 4 Gruppen parallel (`WA_JOBS=4`); Pflicht-Check
  „Ende-zu-Ende-Tests“ nur grün, wenn alle sechs Teile grün sind.
- **Anmeldung über Keycloak (nur CI):** `tests/oidc/` vollständig.
- Dazu Anwendungs-Image und Betriebsskripte (`tests/deploy/`).
- Auf `main` werden die schweren Aufträge übersprungen, wenn der PR genau denselben Inhalt schon vollständig geprüft hat
  ([`docs/release-freigabe.md`](../release-freigabe.md), „Keine Doppelprüfung nach dem Merge“).

Bei Fehlern: Artefakte `e2e-ergebnisse-<speicherart>-teil<k>` bzw. `oidc-ergebnisse` herunterladen (Protokolle und
Bildschirmfotos), Gruppe lokal mit `WA_JOBS=1 python3 tests/run_e2e.py <gruppe>` nachstellen.

Stand: 2026-10-24
