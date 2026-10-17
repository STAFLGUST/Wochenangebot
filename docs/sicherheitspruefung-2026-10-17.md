# Sicherheitsprüfung vom 17.10.2026

## Grundlage und Abgrenzung

Geprüfter Ausgangspunkt: `439843d398d3d1c1f0d0ea10870691ece46f8bcb` (main).
Ausgewertet: API, Sitzungs- und Nutzerverwaltung, zugehörige Oberfläche und Tests,
Docker-/Proxy-Konfiguration, CI sowie bisherige Commits und Pull Requests.
Der referenzierte Chat nennt offene Sicherheitsverbesserungen, enthält aber keinen konkreten
Befundkatalog. Im Repository und den Issues wurde ebenfalls kein solcher Bericht gefunden.
Die folgenden Befunde wurden deshalb am aktuellen Code nachvollzogen. Dies ist eine gezielte
Codeprüfung, kein vollständiger Penetrationstest oder Nachweis der Sicherheit des laufenden VPS.

Bereits vorhanden: Rollenprüfung, CSRF-Tokens, gesperrte Browser-Ersteinrichtung im Produktivbetrieb,
TOTP mit Einmalverwendung, Wiederherstellungscodes, IP-/Passwort-Anmeldesperren,
CSP, anonymisierte Tests und kontrollierte Releases. PR #2 ist ein absichtlicher CI-Negativtest,
kein Beleg für eine offene Bestands-API auf main.

## Umgesetzte Befunde

| Priorität | Befund und Voraussetzung | Korrektur |
| --- | --- | --- |
| Hoch | Mit bekanntem Passwort konnten falsche 2FA-Codes über neue Sitzungen und IP-Adressen wiederholt werden; die Kontosperre zählte nur Passwortfehler. | Gemeinsamer kontobezogener Fehlversuchszähler unter Nutzersperre. Erst eine vollständig erfolgreiche Anmeldung setzt ihn zurück. Auch bereits begonnene 2FA-Anmeldungen beachten die Kontosperre. |
| Hoch | Vor Aktivierung der 2FA bestehende Sitzungen blieben ohne Nachweis des zweiten Faktors gültig. Auch ein Faktorwechsel beendete andere Sitzungen nicht. | Aktivierung, Erneuerung und Abschaltung erhöhen die vorhandene Sitzungsversion und entfernen andere Sitzungen. Die bestätigende Sitzung bleibt nutzbar; alte Anmelde-Challenges werden ungültig. |
| Mittel | Eine vorhandene Sitzung genügte, um einen bestehenden zweiten Faktor durch einen eigenen zu ersetzen. | Erneuerung verlangt erneut das aktuelle Passwort; die vorbereitete Einrichtung ist fünf Minuten gültig und an die Sitzungsversion gebunden. Vor dem Speichern werden Version und Aktivstatus innerhalb der Nutzersperre erneut geprüft. |
| Mittel | Administratoren konnten den eigenen Passwortnachweis bzw. die eigene 2FA-Verwaltung über `user_save` umgehen. | Eigene Passwort- und 2FA-Resets dort serverseitig abgelehnt; die Oberfläche verweist auf den geschützten Passwortwechsel. Namensänderung und Verwaltung anderer Nutzer bleiben möglich. |

Die letzten beiden Maßnahmen begrenzen direkte Umgehungen. Eine vollständig kompromittierte
Administratorsitzung hat weiterhin weitreichende Rechte, einschließlich der Verwaltung anderer
Administratoren. Ein umfassender erneuter Identitätsnachweis für privilegierte Aktionen wäre eine
separate Erweiterung; diese Änderung behauptet keinen vollständigen Schutz gegen Sitzungsdiebstahl.

Bestehende persistente Datenformate bleiben lesbar. Es wird die schon vorhandene `sv` verwendet.
Eine vor dem Update begonnene, noch unbestätigte 2FA-Einrichtung muss neu gestartet werden.
Bei Faktoränderungen müssen sich andere Geräte erneut anmelden.

## Prüfung

Die Gruppe `auth_hardening` prüft direkte HTTP-Anfragen gegen eine frische lokale Testkopie:
Passwortpflicht, Umgehungsversuche, Widerruf alter Sitzungen und Challenges, Recovery-Codes,
Faktorabschaltung und Kontosperre über mehrere simulierte IP-Adressen.
Die bestehende Browsergruppe `security` prüft zusätzlich die Passwortabfrage beim Faktorwechsel,
neue Wiederherstellungscodes und die Abmeldung einer anderen Browsersitzung.
Alle Gruppen sind über `tests/run_e2e.py` automatisch Teil der bestehenden CI.
Lokal bestanden: 38/38 neue HTTP-Prüfungen, 3/3 bestehende Parser-Prüfungen,
PHP-/JavaScript-/Python-Syntax und `git diff --check`. Die Gegenprobe der ersten neun
HTTP-Prüfungen auf dem unveränderten Ausgangscode scheitert in fünf Sicherheitsprüfungen
(4/9 bestanden). Die lokale Chromium-Ausführung wurde durch die macOS-Sandbox blockiert;
die vollständigen Browser- und Betriebsprüfungen laufen in der bestehenden GitHub-CI.
CI-Ergebnisse stehen im zugehörigen Pull Request.

Beim Testen wurde zusätzlich der Standardwert für eine ausgelassene `idleMinutes`-Einstellung
korrigiert: 480 Minuten statt einer PHP-Warnung und versehentlich gespeicherter 0.

## Offen / separat zu behandeln

- Review, grüne CI und anschließend manuelle Freigabe durch den Verantwortlichen; dieser PR
  führt weder Merge noch Release aus.
- Produktionsprüfung der tatsächlichen Proxy-/Netzkonfiguration: `client_ip()` vertraut derzeit
  privaten/reservierten Absenderadressen. Im vorgesehenen Docker-Aufbau ist der PHP-Port nicht
  veröffentlicht und Caddy vorgeschaltet. Daraus folgt kein Nachweis der realen Serverkonfiguration.
  Eine explizite Proxy-Allowlist erfordert eine abgestimmte Betriebsänderung.
- Weitergehender Schutz privilegierter Aktionen mit erneuter Authentifizierung und Begrenzung
  falscher Passwortbestätigungen innerhalb bereits angemeldeter Sitzungen.
- Unabhängiger Blick auf konkurrierende JSON-Schreibvorgänge, insbesondere den IP-Fehlversuchszähler;
  dessen Lese-Ändere-Schreibe-Ablauf ist bislang nicht gesperrt. Die neue kontobezogene Sperre
  verwendet dagegen die bestehende exklusive Nutzersperre.
- Container-Sicherheitsfunde werden in CI derzeit nur berichtet (`exit-code 0`); konkrete Funde
  und geeignete Image-Aktualisierungen müssen separat bewertet und getestet werden.
- Cloud-init-Sperre, Protokoll des fehlgeschlagenen Ubuntu-Updates und vollständiger
  Wiederherstellungstest bleiben Betriebsaufgaben außerhalb dieses PRs.
- Externe Datensicherung ist ausdrücklich verschoben.

Produktionsserver, produktive Daten, Zugangsdaten, Branchschutz und Release-Workflow wurden nicht verändert.

## Erweiterung: sensible Verwaltungsaktionen

- Nach vollständiger Anmeldung gilt eine sitzungsgebundene Freigabe von fünf Minuten. Danach verlangen
  Nutzer-/Kundenverwaltung, Sicherheitsänderungen, Sitzungswiderruf, Entsperren, Mailkonfiguration und
  Versand erneut das aktuelle Passwort. Auch Angebotslöschung und Änderung der öffentlichen Sichtbarkeit
  prüfen diese Freigabe serverseitig. Lesen und normale Angebotsbearbeitung bleiben möglich.
- Ein Dialog erhält die vorbereiteten Eingaben. Erst erfolgreiche Bestätigung wiederholt den ursprünglichen
  Aufruf einmal. Abbrechen führt die Änderung nicht aus. Das Bestätigungspasswort wird weder gespeichert
  noch mit dem ursprünglichen Aufruf erneut übertragen.
- Fünf falsche Passwortbestätigungen sperren diese Bestätigungen kontoweit für zehn Minuten – gemeinsam
  über Passwortwechsel, Faktorwechsel und Verwaltungsbestätigung, unabhängig von Sitzung oder IP.
- Echte Schwachstelle: Passwortprüfungen bei Passwort-/Faktoränderungen hatten bisher keine eigene Bremse.
  Die neue gemeinsame Bremse schließt diesen Rate-Limit-Bypass einer bereits angemeldeten Sitzung.
- Echte Schwachstelle: Anmeldeversuche wurden ohne dieselbe exklusive Dateisperre wie Entsperrungen
  gespeichert; parallele Zugriffe konnten Zähler überschreiben. Schreibzugriffe verwenden jetzt die Sperre.
  Wenn eine Datensperre nicht angelegt/erworben werden kann, bricht die Operation mit HTTP 500 ab.
- Die Freigabe hängt an der Sitzungsversion. Widerruf oder Passwortzurücksetzung durch andere Administratoren
  entwertet auch bestehende Freigaben. Erfolg und Fehlversuche werden ohne Passwort protokolliert.

Tests: direkte HTTP-Regressionen einschließlich Sperrdateifehler und konkurrierendem Dateizugriff sowie
Browserprüfung für Ablauf, Abbruch, Fehlversuch, mobile Darstellung und einmalige Wiederholung.
Neue Gruppen `admin_confirmation` und `admin_confirmation_ui`; vorhandene Gruppen bleiben aktiv.

Offen: bekannte Container-Befunde aus dem bisherigen Bericht, betriebliche Protokoll-Löschfristen und
unabhängige externe Sicherung (auf ausdrücklichen Wunsch verschoben). Keine Änderung am Release-Prozess.
