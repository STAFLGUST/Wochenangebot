# Versandaufträge für Bestellwünsche

Neue Bestellungen speichern die Empfänger und den gerenderten Nachrichteninhalt in `bestellungen.outbox`, atomar mit dem Bestellwunsch. SMTP-Zugangsdaten werden dort nicht gespeichert. Der erste Versand erfolgt weiterhin unmittelbar im Kundenaufruf; es wird kein neuer Serverdienst benötigt. Offene Aufträge bleiben bis zu einem ausdrücklich bestätigten Versandversuch erhalten. Es gibt keinen automatischen periodischen Neuversand.

Je internem Empfänger und optionaler Kundenkopie gibt es einen Auftrag mit Kennung, Zustand, Versuchszähler, Zeit, Fehlerhinweis und Verlauf. Zustände: `queued`, `sending`, `sent`, `failed`. Eine Kundenkopie wird erst versendet, wenn mindestens ein interner Empfänger vom Mailserver bestätigt wurde. Teilfehler sind in der Bestellliste und im Detail sichtbar. `sent` bedeutet SMTP-Annahme, nicht garantierte Zustellung ins Postfach.

Bearbeiter und Administratoren können unter Bestellungen → Detail jeden offenen Auftrag einzeln starten oder nachsenden. Empfänger und Inhalt sind der gespeicherte Originalstand; spätere Einstellungen ändern diese Aufträge nicht. Der aktuelle SMTP-Zugang/Absender wird verwendet. Erfolgreiche Empfänger werden nie über diese Funktion erneut angeschrieben. Eine Wiederholung des Kundenaufrufs erzeugt bei gleicher `requestId` weder neue Aufträge noch E-Mails.

## API

`POST /api/?action=bestellung_mail_retry`, Mitarbeiter-Sitzung (editor/admin), CSRF und JSON erforderlich:

```json
{"nr":"B-2026-0001","jobId":"gespeicherte-kennung","attempts":1,"confirm":true}
```

Die Antwort enthält `order` mit der Mitarbeiteransicht. HTTP 200 bedeutet, dass der Versuch bearbeitet wurde; den Versandzustand in `outbox` prüfen. Ein fehlgeschlagener SMTP-Versuch ist dort `failed`. 409 meldet laufenden Versand, einen veralteten Versuchszähler, bereits erfolgreiche Aufträge oder eine noch gesperrte Kundenkopie. 404 meldet unbekannten Vorgang/Auftrag. 422 meldet unvollständige oder unbestätigte Anforderungen.

Kunden erhalten weder Empfängerlisten, Fehler, Versuchszähler noch Versandverlauf. Mitarbeiterlisten liefern `mailPending`, aber keine Nachrichteninhalte. Mitarbeiterdetails enthalten Zustände/Verlauf, ebenfalls keine gespeicherten HTML-/Textkörper.

## Schutz vor Doppelversand und Unterbrechungen

Eine nicht blockierende Dateisperre pro Bestellnummer verhindert gleichzeitige SMTP-Versuche, auch im SQLite-Modus. Die SQLite-Transaktion läuft nur für das Speichern; sie bleibt nicht während des Netzwerkzugriffs offen. Vor SMTP wird `sending` mit erhöhtem Versuchszähler dauerhaft gespeichert. Ein Prozessabbruch lässt diesen Zustand sichtbar bestehen und gibt die Dateisperre frei. Mitarbeiter müssen vor dem erneuten Versand ausdrücklich bestätigen, dass sie die mögliche vorherige Zustellung geprüft haben. Ein noch laufender Prozess behält die Sperre und verhindert Nachsenden.

Bei SMTP kann nach erfolgreicher Annahme die Rückmeldung verloren gehen. Genau-einmal-Zustellung ist damit nicht garantiert. Es gibt deshalb keinen unbeaufsichtigten Neuversand unklarer Versuche. Auch fehlgeschlagene Versuche benötigen die Bestätigung. Erfolgreiche Aufträge sind gesperrt; veraltete Wiederholungen werden anhand des Versuchszählers abgewiesen.

## Kompatibilität und Betrieb

Bestehende Bestellungen ohne Outbox bleiben lesbar. Empfänger und Versandstatus werden für solche Vorgänge nicht nachträglich geraten; Neuversand ist dort nicht angeboten. Das Datenformat wird nur erweitert, ohne Datenbankmigration. Sicherung und Rückexport erfassen die Aufträge als Teil des bestehenden Bestelldokuments. Datei- und SQLite-Modus werden getestet.

Die ursprünglichen Bestellpositionen, Preise, Bearbeitungsrevision und Statushistorie bleiben beim Nachsenden unverändert. Versandhistorie und SMTP-Ergebnis werden separat geführt. Eine Statusänderung sendet weiterhin keine verbindliche Auftragsbestätigung. Große Bestellmengen, Archivierung und eine allgemeine Warteschlange für andere Mailtypen bleiben separate Schritte.

Prüfungen: `order_outbox` (HTTP, Ausfall/Teilversand, Sperre, unterbrochener Versuch, verlorene SMTP-Bestätigung, Rechte, Originalempfänger), `order_outbox_ui` (mobile Anzeige, Bestätigung, Abbrechen, gezielter Neuversand), bestehende `order_management`, `bestellung` und übrige CI-Suite.
