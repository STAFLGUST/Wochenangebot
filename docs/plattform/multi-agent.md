# Entwicklung mit mehreren KI-Agenten

Ziel: mehrere Agenten arbeiten gleichzeitig an verschiedenen Modulen, ohne sich in gemeinsamen Dateien zu blockieren
und ohne unbemerkt gemeinsame Regeln zu ändern. Verbindliche Kurzfassung: `AGENTS.md`, Abschnitt „Arbeiten mit mehreren Agenten“.

## Rollen

Jedes Modul in `regeln/module.toml` nennt seinen Agenten (`agent`). Startbesetzung:

| Agent | Module | Darf ändern |
| --- | --- | --- |
| dashboard | dashboard | `app/dashboard/**` |
| angebot | angebot | Angebotsdateien laut Register, `app/eingabe/**` |
| bestand, leergut, crm, rewe, einkauf, containerimport, qs, hr, marketing, controlling | je eins | `app/module/<id>/**`, `app/api/module/<id>/**`, eigene Tests |
| verwaltung | verwaltung, import | Verwaltungsdateien laut Register |
| plattform | plattform | Kern, `regeln/`, CI, Betrieb – **koordinationspflichtig** |
| prüfung (H) | – | nichts; prüft PRs (Tests, Sicherheit, Änderungsfolgen), schreibt Befunde |
| mobile | mobile | `mobile/**` |

## Werkzeug `werkzeuge/regeln.py`

| Aufruf | Zweck |
| --- | --- |
| `python3 werkzeuge/regeln.py modul crm` | Steckbrief zu Beginn einer Aufgabe: Oberflächen, Pfade, wohin neuer Code gehört, eigene/fremde Daten, Rechte, Regeln, Tests |
| `python3 werkzeuge/regeln.py betroffen --basis origin/main` | Vor dem PR: betroffene Module, abhängige Module, berührte Daten (und wer sie sonst nutzt), koordinationspflichtige Bereiche, Regeln, zu startende Testgruppen |
| `python3 werkzeuge/regeln.py pruefen` | CI: jede Datei hat einen Eigentümer, jeder Speicherzugriff passt zur Datenverantwortung, jedes Recht und jede Testgruppe ist zugeordnet, Regeln haben existierende Tests, AGENTS.md und Katalog passen zusammen, Wartungstabelle vollständig und widerspruchsfrei, Caddy-Hosts passen zum Register |

Damit erkennt ein CRM-Agent ohne QS-Wissen, wenn seine Änderung Kundenstammdaten (Eigentümer Verwaltung) oder Rechte
(Plattformkern) berührt – die CI lehnt den Zugriff ab, bis er abgestimmt und eingetragen ist.

## Ablauf je Aufgabe

1. `git fetch origin && git worktree add ../wa-<modul> -b agent/<modul>/<thema> origin/main`
2. `python3 werkzeuge/regeln.py modul <modul>` lesen, betroffene Regeln in `regeln/katalog.toml` lesen.
3. Entwickeln; schnelle Prüfung: `python3 werkzeuge/regeln.py pruefen` und die Testgruppen aus `betroffen`.
4. Vor dem PR: die Gruppen aus `betroffen` in beiden Speicherarten; die volle E2E-Suite läuft in der CI (Definition of
   Done), `betroffen`-Ausgabe in den PR-Text; „bereit zum Mergen“ erst mit grüner CI.
5. PR „bereit zum Mergen“; Merge und Release nur durch den Inhaber.

## Konflikte vermeiden

Heutige Sammelstellen und wie sie entschärft werden:

| Sammelstelle | Heute | Ziel |
| --- | --- | --- |
| `app/api/index.php` (Listen der Schreib-/öffentlichen/Wartungs-Aktionen) | jede neue Aktion ändert sie | Module registrieren Aktionen in eigener Datei (Roadmap PR 2) |
| `app/assets/admin.js`, `admin-verwaltung.js` | alle Fachfunktionen | neue Module bekommen eigene Oberflächen unter `app/module/<id>/`; nichts Neues in diese Dateien |
| `tests/run_e2e.py` (`SUITES`) | jede neue Gruppe | Gruppen je Modul registrieren (später `tests/e2e/<modul>/`), bis dahin nur eine Zeile anhängen |
| `app/api/lib/integritaet-liste.php`, Versionsnummern `?v=` | erledigt: nicht mehr im Repository | erzeugt der Server beim Einspielen aus dem freigegebenen Commit (`deploy/bereitstellen.py`); die CI lehnt `?v=` und die Liste im Repository ab |
| `app/api/lib/aktionen-liste.php`, `module-liste.php` | erzeugt aus `regeln/` | bei Konflikt nicht von Hand zusammenführen, sondern nach dem Rebase neu erzeugen (`werkzeuge/regeln.py erzeugen`) |
| `regeln/*.toml` | eine Zeile je neuer Datei/Dokument | Muster je Modul (`app/module/<id>/**`) vorab eingetragen → neue Dateien brauchen meist keinen Eintrag |

Grundregel: Änderungen an koordinationspflichtigen Bereichen (`[[koordination]]`) kommen in eigene, kleine PRs des
Plattform-Agenten – nie nebenbei in einem Fach-PR.

## CODEOWNERS (ADR-6)

Geprüft, vorerst **nicht** eingeführt: Es gibt einen einzigen Prüfer (Inhaber), CODEOWNERS würde nur Pflicht-Reviews
desselben Kontos erzeugen. Die Zuständigkeit steht im Register, die Durchsetzung macht die CI. Sobald weitere Menschen
prüfen, lässt sich `.github/CODEOWNERS` aus `regeln/module.toml` erzeugen (Pfade sind dort schon gepflegt).

## Test- und CI-Konzept

| Ebene | Wo | Was | Daten |
| --- | --- | --- | --- |
| 1 · Agent/PR | lokal im Worktree + GitHub Actions je PR | Regelwerk, Syntax, Unit-, Vertrags- und E2E-Tests, Sicherheitsprüfungen | frisch je Testgruppe aus `tests/fixtures/` (eigene Ports, eigener Datenordner, Test-Mailserver) – keine Produktivdaten, keine echten Zugangsdaten |
| 2 · Integration | eigene Testdomain (ADR-003, mittelfristig; bis dahin CI und `test.angebot-stafl.de`) | Zusammenspiel: Dashboard-Anmeldung, Modulregister, Wartung, Angebot, Stammdaten, Importe | synthetisch (`werkzeuge/testdaten_erzeugen.py`), eigener Container wie `app-test`, nie Zugriff auf Produktionsdaten |
| 3 · Produktion | Release mit Freigabe | nur freigegebene Commits, Healthcheck, Rückfall | echte Daten |

Ebene 1 ist bereits so isoliert, wie es der Auftrag verlangt (jede Gruppe startet einen eigenen PHP-Server mit eigener
Kopie der Testdaten). Darauf aufbauend:

- **Schneller während der Entwicklung:** `betroffen` nennt die Testgruppen; die volle Suite (≈ 10 min je Speicherart)
  bleibt Pflicht in der CI (seit 22.10.2026 nicht mehr zusätzlich lokal – bei mehreren Agenten auf einer Maschine
  kostete das 30–60 min je PR). Keine bestehende Pflichtprüfung wird abgeschaltet.
- **Vertragstests:** die Wartungs-Entscheidungstabelle ist in `regeln/wartung.toml` mit Testfällen hinterlegt; die
  PHP-Umsetzung (Phase 5) muss dieselben Fälle bestehen – eine Definition, zwei Prüfer.
- **Architekturtests:** `werkzeuge/regeln.py pruefen` (Modulgrenzen, Datenverantwortung, Rechte, Caddy ↔ Register).
- **Vorschauumgebungen je PR** (`pr-123.test.dashboard-stafl.de`): auf dem einen Produktiv-VPS **nicht empfohlen** –
  jeder PR-Container teilt CPU/RAM mit dem Echtbetrieb, und Fremdcode eines PR liefe auf dem Produktionsserver. Ebene 1
  läuft vollständig in GitHub Actions; Bildschirmfotos der E2E-Tests sind bei Fehlern als Artefakt verfügbar. Falls
  Vorschauen gewünscht sind: kurzlebig, nur auf Knopfdruck, auf einem getrennten kleinen Test-VPS (Entscheidung E-5).
