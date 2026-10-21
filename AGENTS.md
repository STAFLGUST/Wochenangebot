# Arbeitsregeln für Entwickler und KI-Agenten

Diese Datei ist eine Arbeitsanweisung, keine Sicherheitsgrenze. Durchgesetzt werden die Regeln zusätzlich durch
CI (`.github/workflows/ci.yml`), Branchschutz und den Release-Prozess (`.github/workflows/release.yml`).

**Regelhierarchie** (bei Widerspruch gilt die strengere Regel; Änderungen an 1–3 sind koordinationspflichtig):

1. Diese Datei – Arbeitsweise, Sicherheitsgrenzen, Definition of Done.
2. `regeln/` – maschinenlesbar, von der CI geprüft (`python3 werkzeuge/regeln.py pruefen`):
   `katalog.toml` (Geschäfts- und Architekturregeln GR-xxx mit Tests), `module.toml` (Modulregister, Oberflächen,
   Code-Pfade, Agenten, koordinationspflichtige Bereiche), `datenverantwortung.toml` (Eigentümer jedes
   Speicher-Dokuments), `berechtigungen.toml` (Recht → Modul), `wartung.toml` (Entwicklung/Freigabe/Wartung).
3. `docs/plattform/` – Zielarchitektur und Entscheidungen; `docs/architektur.md` – was heute wo liegt.

## Sicherheitsgrenzen und Grundregeln

1. **Nie direkt nach `main`.** Jede Änderung in einem eigenen Branch und als Pull Request. Zusammenführen und
   Releases freigeben ausschließlich die Verantwortlichen (derzeit: Inhaber des Kontos STAFLGUST).
2. **Produktion nur über Release.** Der Server spielt nur vom Inhaber freigegebene Commits mit grüner CI ein
   (Freigabe in der GitHub-Umgebung `produktion`, `docs/release-freigabe.md`).
   Server, Zugänge, Daten und Deploymentprozess werden nur mit ausdrücklicher Freigabe verändert.
   Ebenso nur mit Freigabe: DNS, Datenbankmigrationen, produktive Freigabe unfertiger Module.
3. **Vor jeder Änderung:** betroffene Geschäftsregeln (`regeln/katalog.toml`) und Tests lesen; einen
   begrenzten Plan machen. Änderungsfolgen ermitteln: `python3 werkzeuge/regeln.py betroffen --basis origin/main`.
4. **Tests:** alle relevanten Tests lokal ausführen (`tests/README.md`), neue Tests für neues Verhalten ergänzen.
   Keine Erfolgsmeldung ohne tatsächlich ausgeführte Tests.
5. **Keine echten Daten, keine Geheimnisse** im Repository (GR-007; Angebote, Bestände, Nutzer, Tokens, Passwörter,
   IP-Adressen). Testdaten nur aus `tests/fixtures/`. Geheimnisse gehören in `.env` auf dem Server.
   Ausnahme: das Postfach-Passwort für den E-Mail-Versand kann ein Administrator im Eingabebereich hinterlegen; es wird
   verschlüsselt gespeichert (Schlüssel `mail-schluessel.php`, nicht in Sicherungen) und nie zurückgegeben.
6. **Datenformate nur erweitern** (GR-006). Code muss bestehende Daten weiter lesen können, damit ein Rückfall auf die
   Vorversion keine Daten beschädigt. Unverträgliche Änderungen brauchen eine eigene Migration mit Freigabe.
7. **Öffentliche Seite:** nie Mengen, Chargen, MHD oder Einkaufspreise ausliefern (GR-001, GR-008).
8. **Kundenangebote:** Preise eines Kundenangebots (`variants`) werden nur aufgelöst und nur an angemeldete,
   berechtigte Nutzer ausgeliefert (`offer_resolve`); das öffentliche Wochenangebot enthält nie Kundenpreise (GR-002).
9. **Kundenzugänge** sind vom Eingabebereich getrennt (GR-003, GR-104): Aktionen des Eingabebereichs prüfen nur die
   Mitarbeiter-Anmeldung (`require_auth`), Kunden (`current_customer`) sehen ausschließlich freigeschaltete Angebote.
   Passwörter nur als Hash, nie in Antworten oder im Protokoll.
10. **Bestellwünsche:** Preise und Summen berechnet ausschließlich der Server aus dem veröffentlichten Angebot des Kunden;
   vom Browser gesendete Preise werden ignoriert (GR-004).
11. **Skripte und Stylesheets:** nach jeder Änderung an `app/assets/` die Versionsnummern mit
   `python3 werkzeuge/asset_versionen.py --setzen` aktualisieren (die CI prüft das), sonst laden Browser alte Kopien.
   Nach jeder Änderung unter `app/` danach die Prüfliste der Dateiprüfung erneuern: `python3 werkzeuge/integritaet.py --setzen`.
12. **Sichtbarkeit und Sonderpreise** (`variants.std` = im Wochenangebot ausgeblendet, `sale`) löst nur der Server in `offer_resolve` auf;
   ausgeliefert wird nie die Sonderpreis-Struktur anderer Angebote. Sonderposten-Mails gehen nur an Kunden des jeweiligen Angebots (GR-005).
13. **Wartung der Angebotsseite** pausiert nur Kundenfunktionen; Mitarbeiter arbeiten weiter (GR-009).

Überblick über Aufbau und Dateien: `docs/architektur.md` (vor Änderungen lesen, nach Umbauten aktualisieren).

## Plattformregeln (STAFL-Plattform, Details in `regeln/katalog.toml`)

- **GR-101 Datenverantwortung:** jedes Speicher-Dokument hat genau einen Eigentümer. Fremde Dokumente nur lesen/schreiben,
  wenn `regeln/datenverantwortung.toml` das erlaubt – neue Dokumente dort registrieren. Neue Querzugriffe sind koordinationspflichtig.
- **GR-102 Entwicklung ≠ Freigabe ≠ Wartung:** wer was nutzen darf, entscheidet nur die Tabelle in `regeln/wartung.toml`.
  Das Beenden einer Wartung macht kein Modul produktiv.
- **GR-103 Autorisierung immer serverseitig:** Kachel, Modulstatus oder ausgeblendete Knöpfe sind nie eine Berechtigung.
  Neue Rechte heißen `<modul>.<recht>`; bestehende Rechte werden nicht umbenannt (gespeicherte Rollenrechte).
- **GR-104 Externe Nutzer** (Kunden, künftig QS-Portal) erhalten nie Zugang zu Mitarbeiter-Oberflächen oder internen APIs.
- **GR-105 Dashboard-Adressen** bleiben 503-Platzhalter, bis das jeweilige Modul freigegeben ist.
- **GR-106 Historische Vorgänge** speichern Schnappschüsse; spätere Stammdatenänderungen ändern sie nicht.
- **GR-107 Wartung je Oberfläche** wirkt serverseitig auf API, Schreiben, Importe, E-Mails und Hintergrundläufe (geplant, Phase 5).
- **Domains und Anmeldung** (`docs/plattform/adr-003-domains-anmeldung.md`): jede Anwendung auf eigener Subdomain.
  **GR-108** nur `__Host-`-Cookies, nie Cookies für alle Subdomains, eigene Sitzung je Host · **GR-109** API nur vom eigenen
  Host (Aktion ↔ Host, `Sec-Fetch-Site`, `Origin`, CSRF, keine CORS-Freigaben) · **GR-110** Mitarbeiteranmeldung nur über
  Keycloak (OIDC), keine eigenen Logins in Modulen · **GR-111** Testumgebungen ohne Produktivsitzungen, -geheimnisse und
  -daten; Keycloak bis zur eigenen Testdomain nur in der CI. GR-108–GR-110 sind geplant; neuer Code hält sie schon ein.

## Arbeiten mit mehreren Agenten

Ablauf und Begründungen: `docs/plattform/multi-agent.md`. Kurzfassung:

1. **Zuständigkeit klären:** `python3 werkzeuge/regeln.py modul <id>` zeigt Pfade, Daten, Rechte, Regeln und Tests eines
   Moduls. Ein Agent ändert nur Dateien seines Moduls (`regeln/module.toml`, Feld `agent`). Neuer Code eines Fachmoduls
   gehört an die Orte unter `pfade_geplant` – nicht in gemeinsame Dateien.
2. **Branch und Arbeitsordner:** Branch `agent/<modul>/<thema>` (Plattformkern: `plattform/<thema>`), eigener Git-Worktree
   (`git worktree add ../wa-<modul> -b agent/<modul>/<thema> origin/main`). Ein Branch = ein Thema = ein PR.
3. **Koordinationspflichtige Bereiche** (`[[koordination]]` in `regeln/module.toml`: Anmeldung, Rechte, Speicherschicht,
   API-Einstieg, Regelwerk, Docker/Caddy/Release, globale Tests): Änderungen nur im eigenen PR mit Abschnitt
   „Koordination“, nicht nebenbei in einem Fach-PR. Kein Agent definiert eine globale Regel unabgestimmt neu.
4. **Änderungsfolgen in den PR:** Ausgabe von `python3 werkzeuge/regeln.py betroffen --basis origin/main` in den PR-Text;
   genannte Regeln, abhängige Module und Testgruppen prüfen.
5. **Schnittstellen statt Durchgriff:** Module nutzen fremde Daten über Funktionen des Eigentümers. Ändert sich eine
   Schnittstelle, nennt der PR alle Nutzer (abhängige Module) und erweitert nur (alte Aufrufe bleiben gültig).
6. **Neue Dateien, Dokumente, Rechte, Testgruppen und API-Aktionen** im selben PR in `regeln/` eintragen – die CI lehnt sonst ab.
   Aktionen stehen in `regeln/aktionen/<modul>.toml` (danach `python3 werkzeuge/regeln.py erzeugen`), nie mehr als Liste in `index.php`.

## Definition of Done (jeder Pull Request)

Ein PR ist erst fertig, wenn alle Punkte erfüllt sind – unabhängig davon, welches Werkzeug oder welche Sitzung ihn
erstellt hat. Unfertige Arbeit wird nicht als Entwurf liegen gelassen, sondern fertiggestellt oder klar als offen beschrieben.

1. Volle E2E-Suite in **beiden** Speicherarten lokal grün (Dateien und `WA_TEST_STORAGE=sqlite`); Ergebnis im PR.
2. Neues Verhalten hat Tests (auch Rechte, Fehler- und Grenzfälle); `tests/README.md` nennt neue Gruppen.
3. Oberfläche per Bildschirmfoto angesehen (Desktop und 390 px Mobil); keine JavaScript-Fehler.
4. Versionsnummern der Assets aktuell (`werkzeuge/asset_versionen.py`), gitleaks ohne Funde.
5. `LIESMICH.md` bzw. `docs/` aktualisiert; PR-Text in Alltagssprache (Vorlage `.github/pull_request_template.md`).
6. PR als „bereit zum Mergen“ markiert; Merge und Release macht ausschließlich der Inhaber.
7. `python3 werkzeuge/regeln.py pruefen` grün; Änderungsfolgen (`betroffen`) im PR; Rückfallweg bzw. Migrationspfad genannt.
8. Im Bericht klar trennen: geplant · implementiert · getestet · gemergt · produktiv ausgerollt.

## Schnell arbeiten, ohne Qualität zu verlieren

- Während der Entwicklung nur betroffene Testgruppen laufen lassen (`python3 tests/run_e2e.py gruppe1 gruppe2`; welche,
  sagt `python3 werkzeuge/regeln.py betroffen`), vor dem PR die volle Suite. Gruppen laufen parallel (`WA_JOBS`,
  Standard 4); zur Fehlersuche `WA_JOBS=1`.
- Tests nie mit festen Wartezeiten prüfen (`wait_for_timeout` vor einem `check`), sondern auf den erwarteten Zustand
  warten (`wait_for_selector`, `wait_for_function`). Der Hintergrundabgleich im Eingabebereich zeigt bei beendeter
  Sitzung jederzeit die Anmeldemaske – Tests dürfen nicht annehmen, dass eine Seite danach bedienbar bleibt.
- Adressen/Ports in Tests nur über `umgebung.py` (`BASE`, `SMTP_PORT`, `SMTP_PORT2`, `AUX_PORT`), nie fest eintragen.
- Volle Ausgabe jeder Gruppe steht in `tests/.arbeit/test-<gruppe>.log` (in der CI als Artefakt bei Fehlern).
- Scheitert eine Gruppe, wiederholt der Testlauf sie einmal allein. Besteht sie dann, bleibt der Lauf grün, aber es
  erscheint die Warnung „wackelig“ (Fehlversuch in `tests/.arbeit/test-<gruppe>-fehlversuch.log`). Solche Gruppen
  zeitnah stabilisieren; zum Aufspüren `WA_RETRY=0 WA_JOBS=5 python3 tests/run_e2e.py` (mehr Last, keine Wiederholung).
