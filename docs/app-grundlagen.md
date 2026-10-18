# Grundlage für eine Kunden- und Mitarbeiter-App

Prüfstand: main 5210c01 (SQLite, Wartungsmodus, gemeinsames Bearbeiten), Oktober 2026.
Die Prüfung betrifft den Repository-Code, nicht die tatsächlich aktivierte Datenablage des VPS.

## Vorhanden und weiterverwendbar

- Zentrale PHP-JSON-API; Browser und zukünftige App sollen dieselben Geschäftsregeln verwenden.
- SQLite mit expliziter Migration, Sicherung und Rückexport; Dateien bleiben als kompatible Alternative.
- Serverseitig berechnete Kundenpreise; getrennte Kunden- und Mitarbeiter-Sitzungen, CSRF-Schutz,
  Mitarbeiterrollen, 2FA, Sitzungswiderruf und zusätzliche Bestätigung sensibler Admin-Aktionen.
- Neue Bestellfunktionen sind serverseitig implementiert. Sie benötigen kein DOM und keine Browserdaten
  zur Autorisierung. Listen sind begrenzt/paginiert; Details prüfen die Berechtigung am einzelnen Vorgang.
- Gespeicherte Bestellpositionen sind historische Schnappschüsse. Neue Angebote verändern sie nicht.
- Wiederholbare Übermittlung mit `requestId`, damit ein Verbindungsabbruch keine zweite Bestellung
  und keine zweite E-Mail erzeugt. Der Webclient behält die Kennung bis zur erhaltenen Erfolgsantwort.

## Umfang dieses PRs

Mitarbeiter mit Rolle editor/admin sehen und bearbeiten Bestellwünsche: Suche, Status, Zuständigkeit,
interne Notiz, Änderungsverlauf. Kunden sehen ausschließlich eigene Vorgänge und den Bearbeitungsstand.
Interne Notizen, Mitarbeiterdaten, technische Versandfehler und Wiederholungsschlüssel werden nicht an
Kunden ausgeliefert. Versandstatus bleibt vom Bearbeitungsstatus getrennt. Status „Bestätigt“ ist eine
interne Kennzeichnung, keine automatisch versandte verbindliche Auftragsbestätigung.

Änderungen verwenden eine Revision; veraltete Geräte erhalten HTTP 409 statt fremde Änderungen zu
überschreiben. Alte Vorgänge werden als „neu“ dargestellt; fehlende Kontaktschnappschüsse werden nicht
nachträglich erfunden. Neue Vorgänge speichern die damaligen Kontaktdaten. Die bisherige stille Kürzung
auf 5.000 Bestellungen entfällt, damit offene Vorgänge und Wiederholungskennungen nicht verloren gehen.

## Bewusste Grenzen und nächste App-Schritte

1. PWA oder native iOS/Android-App entscheiden. Eine native App benötigt ein eigenes, geprüftes
   Anmeldekonzept; vorzugsweise Authorization Code mit PKCE über den Systembrowser, einen geeigneten
   Identity-Provider und widerrufbare Gerätesitzungen. Dieser PR führt keine selbstgebauten langlebigen
   Zugriffstokens ein und öffnet CORS nicht pauschal. Die vorhandene Cookie-/CSRF-Anmeldung bleibt erhalten.
2. Vor App-Veröffentlichung stabile API-Verträge ausbauen: Authentifizierung, Angebote, Artikel und
   Merkliste neben dem dokumentierten Bestellvertrag. API-Version 1 bezeichnet hier das neue Antwortformat,
   keine bereits vollständige REST-/OAuth-Plattform.
3. Offline zunächst nur Entwürfe lokal halten; verbindliche Preise und Berechtigungen beim Absenden
   erneut serverseitig prüfen. Keine Preisgarantie für offline gespeicherte Angebote.
4. Die [Bestell-Outbox](bestell-mailversand.md) speichert jetzt einzelne Empfängerzustände und erlaubt
   ausdrücklich bestätigten Neuversand. Eine exakt einmalige SMTP-Zustellung bleibt unmöglich.
   Ein Hintergrunddienst und die Ausweitung auf andere Mailtypen sind separate Schritte.
5. Bei wachsender Bestellmenge auf Einzeldatensätze/SQL-Indizes umstellen. Der aktuelle SQLite-Adapter
   speichert weiterhin JSON-Dokumente; Pagination begrenzt Antworten, nicht die intern eingelesene Liste.
   Aufbewahrung und Archivierung fachlich festlegen, statt alte Bestellungen still zu löschen.
6. Push-Mitteilungen, App-Store-Veröffentlichung, gerätesichere Zugangsspeicherung, Barrierefreiheit und
   Betriebsüberwachung separat planen. Kein App-Deployment oder Produktionsumbau in diesem PR.

Orientierung: [OWASP – Zugriff auf einzelne API-Objekte](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/)
und [RFC 8252 – Anmeldung nativer Apps](https://www.rfc-editor.org/info/rfc8252/).
