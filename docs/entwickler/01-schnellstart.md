# 1 · Schnellstart

Vom leeren Rechner bis zum ersten Pull Request. Grundregeln vorab (verbindlich in [`AGENTS.md`](../../AGENTS.md)):
nie direkt nach `main`, nur Testdaten, keine Geheimnisse im Repository (es ist öffentlich), Produktion nur über
einen vom Inhaber freigegebenen Release.

## Voraussetzungen

| Werkzeug | Wofür | Hinweis |
| --- | --- | --- |
| Git | Quelltext, Branches, Worktrees | |
| PHP 8.3 (CLI) mit `mbstring`, `openssl`, `sodium`, `pdo_sqlite`/`sqlite3` | Anwendung und Testserver (`php -S`) | wie das Server-Image `php:8.3-apache` |
| Python 3.12 | Werkzeuge (`werkzeuge/*.py`, nur Standardbibliothek), Testläufe | `tomllib` ab 3.11 |
| Python-Pakete aus `tests/requirements.txt` | Playwright, openpyxl, cryptography | `python3 -m pip install -r tests/requirements.txt` |
| Chromium für Playwright | Oberflächentests | `python3 -m playwright install --with-deps chromium` |
| Node.js | Syntaxprüfung und Unit-Tests der Skripte (`node --check`, `tests/unit/*.test.js`) | kein npm, kein Build |
| optional: shellcheck, actionlint, gitleaks | wie die CI | |

Es gibt **kein Framework, keinen Paketmanager und keinen Build-Schritt** – PHP, HTML, CSS und JavaScript werden so
ausgeliefert, wie sie im Repository stehen.

## Lokal starten

```bash
git clone https://github.com/STAFLGUST/Wochenangebot.git && cd Wochenangebot
python3 werkzeuge/lokal.py            # http://127.0.0.1:8080 mit Testdaten
```

`werkzeuge/lokal.py` baut einen Server wie die Testsuite: Kopie von `app/` in `tests/.arbeit/lokal/` (mit
Versionsnummern wie auf dem Server), Testdaten aus `tests/fixtures/data-seed`, Dashboard unter `/dashboard/`, Zugang
`admin` mit dem Testpasswort (wird beim Start angezeigt). Optionen: `--port`, `--leer` (ohne Beispieldaten),
`--sqlite` (Speicher SQLite), `--passwort`. Änderungen an `app/` wirken erst nach einem Neustart.

| Adresse | Oberfläche |
| --- | --- |
| `/` | Kundenseite mit dem Wochenangebot |
| `/admin/` | Eingabebereich (lokal mit Passwort-Anmeldung; in Produktion über Keycloak) |
| `/dashboard/` | Mitarbeiter-Dashboard |
| `/module/hr/`, `/module/crm/`, `/module/marketing/`, `/module/controlling/`, `/module/leergut/`, `/module/rewe/` | Modulseiten HR, CRM, Marketing, Controlling, Leergut und REWE |

Lokal fehlt die zentrale Anmeldung über Keycloak (sie läuft nur in der CI-Testumgebung `tests/oidc/`, siehe
[07 Tests](07-tests.md)); deshalb gibt es lokal einen Bereich-Host nicht, und alle Ansichten erscheinen in einem
Eingabebereich. Wie sich die Oberflächen je Host unterscheiden: [02 Architektur](02-architektur.md).

## Erster Test

```bash
python3 tests/run_e2e.py rechte rollen          # zwei Testgruppen, je ein eigener Testserver
WA_TEST_STORAGE=sqlite python3 tests/run_e2e.py rechte rollen
python3 werkzeuge/regeln.py pruefen             # Regelwerk und Modulgrenzen
python3 werkzeuge/doku.py pruefen               # Dokumentation passt zum Code
```

Welche Gruppen eine Änderung betrifft, sagt `python3 werkzeuge/regeln.py betroffen --basis origin/main`. Ausgaben
stehen in `tests/.arbeit/test-<gruppe>.log`, Bildschirmfotos in `tests/.ergebnisse/`. Mehr: [07 Tests](07-tests.md).

## Erster Pull Request

```bash
git fetch origin
git worktree add ../wa-<thema> -b plattform/<thema> origin/main    # Fachmodul: agent/<modul>/<thema>
cd ../wa-<thema>
# … ändern …
python3 werkzeuge/regeln.py erzeugen     # nur wenn regeln/ geändert (Aktionen, Module)
python3 werkzeuge/doku.py erzeugen       # Referenz der Dokumentation neu schreiben
python3 werkzeuge/regeln.py pruefen && python3 werkzeuge/doku.py pruefen
python3 tests/run_e2e.py <betroffene Gruppen>   # dann dieselben mit WA_TEST_STORAGE=sqlite
git commit … && git push -u origin plattform/<thema>
```

Den Pull Request nach der Vorlage [`.github/pull_request_template.md`](../../.github/pull_request_template.md) in
Alltagssprache beschreiben, mit Änderungsfolgen (`betroffen`), Testergebnissen (lokal und CI) und Rückfallweg.
Mergen und Releases freigeben macht ausschließlich der Inhaber. Ablauf danach: [08 Betrieb](08-betrieb.md).

## Wo anfangen?

1. [02 Architektur](02-architektur.md) lesen.
2. Steckbrief des Moduls, an dem gearbeitet wird: `python3 werkzeuge/regeln.py modul <id>` (Pfade, Daten, Rechte,
   Regeln, Tests) und [Referenz: Module](referenz/module.md).
3. Geschäftsregeln in [`regeln/katalog.toml`](../../regeln/katalog.toml) und die Tests des Bereichs lesen.
4. Für typische Aufgaben gibt es [09 Anleitungen](09-anleitungen.md).

Stand: 2026-10-24
