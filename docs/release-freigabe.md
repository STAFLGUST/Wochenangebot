# Release freigeben

Neue Stände gehen nur live, wenn der Inhaber sie ausdrücklich freigibt. Die Freigabe ist ein Klick in GitHub.

## Ablauf

1. PR mergen (optional vorher in der Testumgebung prüfen, siehe `docs/testumgebung.md`).
2. Die CI läuft auf `main`. Ist sie grün, startet sie den Release-Lauf (Job „Release zur Freigabe vorlegen“).
   Hat die CI des Pull Requests genau denselben Inhalt schon vollständig geprüft (Normalfall), dauert das etwa
   1 Minute statt 6–30 Minuten – siehe „Keine Doppelprüfung nach dem Merge“.
3. Der Release-Lauf **wartet** in der GitHub-Umgebung `produktion`. Die eingetragenen Prüfer bekommen eine
   E-Mail bzw. eine Meldung in der GitHub-App („Deployment review requested“).
4. Freigeben: Lauf öffnen → **Review deployments** → Haken bei `produktion` → **Approve and deploy**.
   Ablehnen: **Reject**. Wer nichts tut, gibt nichts frei.
5. Nach der Freigabe prüft der Lauf noch einmal, legt dann die Markierung `release-…` an. Der Server übernimmt
   den Stand innerhalb von etwa 2 Minuten (`deploy/freigabe-einspielen.sh`: Sicherung, Healthcheck, Rückfall).

Von Hand starten geht weiterhin: Actions → **Release** → **Run workflow** (Branch `main`, Grund eintragen). Auch
dann wartet der Lauf auf die Freigabe.

**Keine Freigabeanfrage nach dem Merge?** Nur der automatische CI-Lauf nach dem Merge (Ereignis „push“) legt den Release
vor. Wurde die CI auf `main` von Hand gestartet (Actions → CI → Run workflow) oder kam der automatische Lauf nicht,
den Release wie oben von Hand starten – der Release prüft selbst, dass es für genau diesen Commit eine grüne CI gibt.
CI-Läufe auf `main` brechen sich nicht gegenseitig ab, sondern warten aufeinander (`concurrency` in `ci.yml`).

## Keine Doppelprüfung nach dem Merge

Die CI eines Pull Requests prüft nicht den Branch allein, sondern den Stand **nach** dem Zusammenführen mit `main`
(`refs/pull/N/merge`). Weil `main` nur mit aktuellem Branch zusammengeführt werden darf (Branchschutz „up to date“),
ist der Inhalt nach dem Merge in aller Regel Byte für Byte derselbe (gleicher Git-Tree; nachgeprüft für PR #92, #94, #95).
Eine zweite volle Prüfung auf `main` bringt dann nichts Neues, kostete aber 15–30 Minuten und staute weitere Merges.

So läuft es jetzt (`ci.yml`, `.github/scripts/ci_nachweis.py`):

1. **Im Pull Request** läuft die volle CI. Sind alle Aufträge grün, hält der letzte Auftrag den geprüften Inhalt fest:
   „Vollständig geprüft (Stand `<Tree>`)“.
2. **Nach dem Merge auf `main`** fragt der Auftrag „Schon im Pull Request geprüft?“ die GitHub-API: Gibt es einen
   erfolgreichen CI-Lauf eines Pull Requests **aus diesem Repository** (kein Fork), dessen Kopf-Commit zu diesem Merge
   gehört, in dem **alle** Aufträge grün sind und „Vollständig geprüft“ **genau den Tree** des neuen `main`-Commits nennt?
   - **Ja** → Anwendungs-Image, Sicherung/Release-Prozess, Ende-zu-Ende-Tests und Keycloak werden übersprungen;
     der Auftrag „Prüfung aus Pull Request übernommen“ verlinkt den Pull-Request-Lauf; der Release wird sofort vorgelegt.
     Statische Prüfungen und Secret-Scan (je ~20 s) laufen trotzdem.
   - **Nein oder unklar** (z. B. `main` hat sich seit dem PR-Lauf bewegt → anderer Tree, Lauf aus der Zeit vor dieser
     Änderung, API-Fehler) → volle CI wie bisher.
3. Verglichen werden nur Hashes, Namen und Ergebnisse über die API – kein Code und keine Dateien aus anderen Läufen.
4. **Release-Prüfung** (`release-pruefen.sh ci`): ein erfolgreicher CI-Lauf zählt nur, wenn er den Auftrag „Vollständig
   geprüft (Stand …)“ **oder** „Prüfung aus Pull Request übernommen“ erfolgreich enthält. Ein Lauf, in dem nur
   übersprungen wurde, reicht nie für einen Release.

**Woran man es erkennt:** Im CI-Lauf auf `main` steht der Auftrag „Prüfung aus Pull Request übernommen“ (grün) mit
Link zum Pull-Request-Lauf; die schweren Aufträge sind grau (übersprungen); der Release-Lauf wartet nach etwa einer
Minute auf die Freigabe. Bei voller CI steht stattdessen am Ende „Vollständig geprüft (Stand …)“; der Grund steht in
der Zusammenfassung des Auftrags „Schon im Pull Request geprüft?“.

**Vorher ausprobieren (ändert nichts):** Actions → **CI-Nachweis (Trockenlauf)** → Run workflow (Branch `main`,
optional einen Commit eintragen) – zeigt, ob übernommen würde und warum (nicht). Lokal mit `gh`:
`GITHUB_REPOSITORY=STAFLGUST/Wochenangebot python3 .github/scripts/ci_nachweis.py --sha <commit> --trockenlauf`.

**Volle CI auf main erzwingen:** Actions → CI → Run workflow (Branch `main`). Von Hand gestartete Läufe prüfen immer
vollständig; danach den Release von Hand starten (siehe oben).

**Zurück zum alten Verhalten:** im Auftrag „Schon im Pull Request geprüft?“ den Schritt „… suchen (nur main)“ entfernen
(ohne Ausgabe `uebernommen=true` läuft immer die volle CI) – oder den PR „CI schneller“ zurücknehmen.

### Laufzeiten (gemessen 22.10.2026)

| | vorher | nachher |
| --- | --- | --- |
| CI eines Pull Requests | 6–19 Min. (Engpass: Paket-Downloads mit 30–60 kB/s; Keycloak 6–23, E2E 5–13 Min.) | ~6–7 Min., gleichmäßig (Keycloak ~6 Min., E2E-Teile je 2–2,7 Min.) |
| CI auf `main` nach dem Merge | 6–30 Min., mehrere Merges nacheinander | ~1 Min. bei gleichem Inhalt (Normalfall), sonst wie PR |
| Merge → Freigabeanfrage | 6–30 Min. (+ Wartezeit auf vorherige Läufe) | ~1–2 Min. |

Beschleunigt außerdem: Ende-zu-Ende-Tests in 3 Teilen je Speicherart (`tests/README.md`), Paketvorrat und
Keycloak/Caddy im Zwischenspeicher (Workflow „Zwischenspeicher“, `.github/scripts/testumgebung.sh`). Pakete aus dem
Zwischenspeicher werden nur mit passender Prüfsumme aus der signierten Ubuntu-Paketliste verwendet
(`.github/scripts/apt_vorrat.py`), Keycloak/Caddy nur mit der festen Prüfsumme aus `tests/oidc/umgebung.sh`.

## Was der Server beim Einspielen macht (`deploy/freigabe-einspielen.sh`)

1. Prüft Release-Lauf, CI und dass der Commit auf `main` liegt.
2. **Anwendungs-Image** (nur wenn das Release Dateien unter `deploy/image/` ändert und `COMPOSE_FILE` in `.env` die
   Ergänzungsdatei `deploy/anmeldung/docker-compose.anmeldung.yml` enthält): baut das Image des neuen Stands vorab
   (`docker compose build --pull app`, als `stafl-app:release-neu`). App-Code und laufende Container bleiben dabei
   unverändert. Schlägt der Bau fehl, wird nichts eingespielt; Meldung im Eingabebereich, nächster Versuch beim
   nächsten Lauf (alle 2 Minuten). So kommen Sicherheitsupdates des Basis-Images (neuer Digest) wirklich an.
3. **Sicherung** mit dem Sicherungsskript des **neuen** Commits (`deploy/.sichern-release.sh`, wird danach gelöscht;
   fehlt das Skript im neuen Commit, das vorhandene). Ein Fehler im alten Skript blockiert so nicht mehr das Release,
   das ihn behebt. Die Hilfsdateien in `deploy/` (`datenbank.py`, `sicherung-pruefen.*`) stammen dabei noch aus dem
   alten Stand. Ohne Sicherung kein Release.
4. Code wechseln. Alle Container werden neu erstellt, wenn sich `Caddyfile`, `docker-compose.yml` oder die
   Ergänzungsdatei ändern; wurde in Schritt 2 nur das Image gebaut, nur die App (Keycloak läuft weiter). Das bisherige
   Image bleibt als `stafl-app:release-vorher` erhalten.
   Direkt danach **Bereitstellung** (`deploy/bereitstellen.py` des neuen Stands): Versionsnummern der Skripte/Stylesheets
   und Prüfliste der Dateiprüfung aus den Git-Objekten genau dieses Commits (siehe unten). Ein Fehler dabei verhindert das
   Release nicht – die Seite lädt Dateien ohne Nummer mit Rückfrage, `aktualisieren.sh` holt die Bereitstellung nach.
5. Healthcheck wie ein Besucher. Schlägt er fehl: zurück auf den alten Commit, das alte Image wieder aktiv
   (`stafl-app:release-vorher` → aktiver Name), Container neu erstellt.
6. Nach erfolgreichem Healthcheck: `docker image prune -f` entfernt nur hängende Images ohne Namen (z. B. das von
   `release-vorher` verdrängte). Getaggte und laufende Images sowie Volumes bleiben unberührt; ein Fehler beim Aufräumen
   ändert nichts am erfolgreichen Release (nur ein Hinweis im Protokoll).

Getestet ohne Docker in `tests/deploy/test_freigabe.sh`.

## Versionsnummern und Prüfliste (`deploy/bereitstellen.py`)

Früher standen beide im Repository und lösten bei fast jedem Pull Request Merge-Konflikte aus. Jetzt erzeugt sie der
Server aus dem eingespielten (also freigegebenen, CI-geprüften) Commit:

- **Versionsnummern** `?v=…` = SHA-256 des Dateiinhalts (10 Zeichen), wie früher – gleiche Adressen, gleiches
  Zwischenspeichern (Caddy: mit `?v=` ein Jahr, sonst `no-cache`). Eine geänderte Datei bekommt eine neue Adresse, der
  Browser lädt sie sofort. Fehlt eine Nummer, fragt der Browser beim Server nach – nie eine veraltete Kopie.
- **Prüfliste** `app/api/lib/integritaet-liste.php` (nicht versioniert, `.gitignore`): gelesen aus den Git-Objekten des
  Commits, nicht aus dem Arbeitsordner – veränderte oder zusätzliche Dateien werden nie als freigegeben übernommen; sie
  liegt im nur lesend eingebundenen Programmordner. HTML-Seiten stehen mit beiden Fassungen darin (mit/ohne Nummern).
- Läuft nach jedem Codewechsel (Release, automatischer und manueller Rückfall, `testumgebung.sh einspielen`,
  `einrichten.sh`) und bei jedem Lauf von `aktualisieren.sh` (alle 2 Minuten; schreibt nur, wenn etwas fehlt). Eine Seite
  wird nur ergänzt, wenn sie genau dem Commit entspricht; anders veränderte Dateien bleiben stehen und die Dateiprüfung
  meldet sie.
- Stände von vor der Umstellung enthalten Liste und Nummern selbst – dann ändert das Skript nichts (Rückfall).
- **Übergang:** Den ersten Release mit `bereitstellen.py` spielt noch das alte Skript ein. Bis zum nächsten Lauf von
  `aktualisieren.sh` (höchstens 2 Minuten) fehlen Nummern (Dateien werden mit Rückfrage geladen) und Prüfliste (eine
  Dateiprüfung in diesem Moment meldet „Prüfliste fehlt“). Keine Serverschritte nötig.
- Prüfen von Hand: `python3 deploy/bereitstellen.py --pruefen` (entspricht `app/` dem bereitgestellten Stand?).

## Notfall-Rückfall von Hand (`deploy/release-zurueck.sh`)

`sh /opt/wochenangebot/deploy/release-zurueck.sh` geht auf den Stand vor dem letzten Release zurück (`vorher` in
`daten/deployment.php`); Daten bleiben unverändert, der zurückgenommene Stand wird nicht erneut automatisch eingespielt.
Danach Versionsnummern und Prüfliste des zurückgeholten Stands (`deploy/bereitstellen.py`). Container und Image wie beim
automatischen Rückfall:

- `Caddyfile`, `docker-compose.yml` oder die Ergänzungsdatei der Anmeldung unterscheiden sich → alle Container neu.
- `deploy/image/` unterscheidet sich und `COMPOSE_FILE` enthält die Ergänzungsdatei → `stafl-app:release-vorher` wieder
  auf den aktiven Namen, nur die App neu. Fehlt das gemerkte Image, meldet das Skript das und baut das Image aus dem
  Bauplan des vorherigen Stands (`docker compose build app`); scheitert der Bau (oder das Taggen), bricht es ab – Code
  und Container bleiben unverändert.
- Gesperrt: Rückfall auf einen abgelehnten bzw. automatisch zurückgenommenen Release (steht nach einem automatischen
  Rückfall als `vorher` im Status) und, solange SQLite aktiv ist, auf Code ohne Speicherschicht (`docs/datenbank.md`).

## Was der Lauf nach der Freigabe prüft (`.github/scripts/release-pruefen.sh`)

| Prüfung | Abbruch, wenn … |
| --- | --- |
| Freigabepflicht | die Umgebung `produktion` keine Prüfer verlangt (Schutz gegen versehentliches Abschalten) |
| Aktueller Stand | `main` inzwischen weiter ist – dann wartet bereits ein neuerer Lauf |
| CI | die CI für genau diesen Commit nicht erfolgreich war oder keinen Nachweis enthält („Vollständig geprüft (Stand …)“ bzw. „Prüfung aus Pull Request übernommen“); läuft sie noch, wartet der Lauf bis 10 Minuten |

Es wartet immer nur der neueste Lauf: Ein neuer Merge beendet einen älteren, noch nicht freigegebenen Lauf
(Status „abgebrochen“). Das Protokoll (Tag-Beschreibung) nennt, wer freigegeben hat.

Der Server bleibt unverändert: Er übernimmt nur den neuesten erfolgreichen Release-Lauf auf `main` und prüft die
CI selbst noch einmal.

## Einmalige Einrichtung in GitHub (nur Inhaber)

Settings → Environments → **New environment** → Name `produktion` → **Configure environment**:

- **Required reviewers**: anhaken, `STAFLGUST` eintragen. „Prevent self-review“ **nicht** anhaken (der Inhaber
  merged und gibt selbst frei).
- **Deployment branches and tags**: „Selected branches and tags“ → Regel `main`.
- **Save protection rules**.

Fehlt die Umgebung oder der Prüfer, bricht jeder Release-Lauf mit einem Hinweis ab – es wird dann nichts
veröffentlicht.

Benachrichtigungen: GitHub → Settings → Notifications → „Actions“ bzw. „Deployment review“ per E-Mail/App aktiv.
