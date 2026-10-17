# Arbeitsregeln für Entwickler und KI-Agenten

Diese Datei ist eine Arbeitsanweisung, keine Sicherheitsgrenze. Durchgesetzt werden die Regeln zusätzlich durch
CI (`.github/workflows/ci.yml`), Branchschutz und den Release-Prozess (`.github/workflows/release.yml`).

1. **Nie direkt nach `main`.** Jede Änderung in einem eigenen Branch und als Pull Request. Zusammenführen und
   Releases starten ausschließlich die Verantwortlichen (derzeit: Inhaber des Kontos STAFLGUST).
2. **Produktion nur über Release.** Der Server spielt nur von Hand freigegebene Commits mit grüner CI ein.
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
