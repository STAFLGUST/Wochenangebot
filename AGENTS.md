# Arbeitsregeln für Entwickler und KI-Agenten

Diese Datei ist eine Arbeitsanweisung, keine Sicherheitsgrenze. Durchgesetzt werden die Regeln zusätzlich durch
CI (`.github/workflows/ci.yml`), Branchschutz und den Release-Prozess (`.github/workflows/release.yml`).

1. **Nie direkt nach `main`.** Jede Änderung in einem eigenen Branch und als Pull Request. Zusammenführen und
   Releases freigeben ausschließlich die Verantwortlichen (derzeit: Inhaber des Kontos STAFLGUST).
2. **Produktion nur über Release.** Der Server spielt nur vom Inhaber freigegebene Commits mit grüner CI ein
   (Freigabe in der GitHub-Umgebung `produktion`, `docs/release-freigabe.md`).
   Server, Zugänge, Daten und Deploymentprozess werden nur mit ausdrücklicher Freigabe verändert.
3. **Vor jeder Änderung:** betroffene Geschäftsregeln (künftig `regeln/katalog.yaml`) und Tests lesen; einen
   begrenzten Plan machen.
4. **Tests:** alle relevanten Tests lokal ausführen (`tests/README.md`), neue Tests für neues Verhalten ergänzen.
   Keine Erfolgsmeldung ohne tatsächlich ausgeführte Tests.
5. **Keine echten Daten, keine Geheimnisse** im Repository (Angebote, Bestände, Nutzer, Tokens, Passwörter,
   IP-Adressen). Testdaten nur aus `tests/fixtures/`. Geheimnisse gehören in `.env` auf dem Server.
   Ausnahme: das Postfach-Passwort für den E-Mail-Versand kann ein Administrator im Eingabebereich hinterlegen; es wird
   verschlüsselt gespeichert (Schlüssel `mail-schluessel.php`, nicht in Sicherungen) und nie zurückgegeben.
6. **Datenformate nur erweitern.** Code muss bestehende Daten weiter lesen können, damit ein Rückfall auf die
   Vorversion keine Daten beschädigt. Unverträgliche Änderungen brauchen eine eigene Migration mit Freigabe.
7. **Öffentliche Seite:** nie Mengen, Chargen, MHD oder Einkaufspreise ausliefern.
8. **Kundenangebote:** Preise eines Kundenangebots (`variants`) werden nur aufgelöst und nur an angemeldete,
   berechtigte Nutzer ausgeliefert (`offer_resolve`); das öffentliche Wochenangebot enthält nie Kundenpreise.
9. **Kundenzugänge** sind vom Eingabebereich getrennt: Aktionen des Eingabebereichs prüfen nur die Mitarbeiter-Anmeldung
   (`require_auth`), Kunden (`current_customer`) sehen ausschließlich freigeschaltete Angebote. Passwörter nur als Hash,
   nie in Antworten oder im Protokoll.
10. **Bestellwünsche:** Preise und Summen berechnet ausschließlich der Server aus dem veröffentlichten Angebot des Kunden;
   vom Browser gesendete Preise werden ignoriert.
11. **Skripte und Stylesheets:** nach jeder Änderung an `app/assets/` die Versionsnummern mit
   `python3 werkzeuge/asset_versionen.py --setzen` aktualisieren (die CI prüft das), sonst laden Browser alte Kopien.
12. **Sichtbarkeit und Sonderpreise** (`variants.std` = im Wochenangebot ausgeblendet, `sale`) löst nur der Server in `offer_resolve` auf;
   ausgeliefert wird nie die Sonderpreis-Struktur anderer Angebote. Sonderposten-Mails gehen nur an Kunden des jeweiligen Angebots.

Überblick über Aufbau und Dateien: `docs/architektur.md` (vor Änderungen lesen, nach Umbauten aktualisieren).

## Definition of Done (jeder Pull Request)

Ein PR ist erst fertig, wenn alle Punkte erfüllt sind – unabhängig davon, welches Werkzeug oder welche Sitzung ihn
erstellt hat. Unfertige Arbeit wird nicht als Entwurf liegen gelassen, sondern fertiggestellt oder klar als offen beschrieben.

1. Volle E2E-Suite in **beiden** Speicherarten lokal grün (Dateien und `WA_TEST_STORAGE=sqlite`); Ergebnis im PR.
2. Neues Verhalten hat Tests (auch Rechte, Fehler- und Grenzfälle); `tests/README.md` nennt neue Gruppen.
3. Oberfläche per Bildschirmfoto angesehen (Desktop und 390 px Mobil); keine JavaScript-Fehler.
4. Versionsnummern der Assets aktuell (`werkzeuge/asset_versionen.py`), gitleaks ohne Funde.
5. `LIESMICH.md` bzw. `docs/` aktualisiert; PR-Text in Alltagssprache (Vorlage `.github/pull_request_template.md`).
6. PR als „bereit zum Mergen“ markiert; Merge und Release macht ausschließlich der Inhaber.

## Schnell arbeiten, ohne Qualität zu verlieren

- Während der Entwicklung nur betroffene Testgruppen laufen lassen (`python3 tests/run_e2e.py gruppe1 gruppe2`), vor dem
  PR die volle Suite. Gruppen laufen parallel (`WA_JOBS`, Standard 4); zur Fehlersuche `WA_JOBS=1`.
- Tests nie mit festen Wartezeiten prüfen (`wait_for_timeout` vor einem `check`), sondern auf den erwarteten Zustand
  warten (`wait_for_selector`, `wait_for_function`). Der Hintergrundabgleich im Eingabebereich zeigt bei beendeter
  Sitzung jederzeit die Anmeldemaske – Tests dürfen nicht annehmen, dass eine Seite danach bedienbar bleibt.
- Adressen/Ports in Tests nur über `umgebung.py` (`BASE`, `SMTP_PORT`, `SMTP_PORT2`, `AUX_PORT`), nie fest eintragen.
- Volle Ausgabe jeder Gruppe steht in `tests/.arbeit/test-<gruppe>.log` (in der CI als Artefakt bei Fehlern).
- Scheitert eine Gruppe, wiederholt der Testlauf sie einmal allein. Besteht sie dann, bleibt der Lauf grün, aber es
  erscheint die Warnung „wackelig“ (Fehlversuch in `tests/.arbeit/test-<gruppe>-fehlversuch.log`). Solche Gruppen
  zeitnah stabilisieren; zum Aufspüren `WA_RETRY=0 WA_JOBS=5 python3 tests/run_e2e.py` (mehr Last, keine Wiederholung).

