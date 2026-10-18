# Bestell-API, Antwortformat 1

Basis: `/api/?action=…`, JSON, HTTPS. Alle neuen erfolgreichen Antworten enthalten `ok: true` und
`apiVersion: 1`. Fehler verwenden HTTP-Status und `{ "ok": false, "error": "…" }`.
Authentifizierung: bestehende Sitzungs-Cookies. POST benötigt `Content-Type: application/json` und
`X-CSRF-Token` aus der passenden Mitarbeiter- oder Kundenanmeldung. Kein Admin-Token im App-Code.
Kundenlisten/-details folgen auch den bestehenden Wartungs- und Länderregeln.

| Aktion | Methode | Berechtigung | Eingabe |
| --- | --- | --- | --- |
| bestellungen | GET | editor/admin | q, workflow, offset, limit (1–100; Standard 25) |
| bestellung | GET | editor/admin | nr |
| bestellung_save | POST | editor/admin | nr, revision (Integer), workflow, assignee (Nutzer-ID oder leer), note (max. 2.000 Zeichen) |
| kunde_bestellungen | GET | angemeldeter Kunde ohne Passwortwechselpflicht | q, workflow, offset, limit |
| kunde_bestellung_detail | GET | Eigentümer des Vorgangs | nr |
| kunde_bestellung | POST | bestehende Kundenberechtigung | bisherige Felder + optional requestId (16–80 Zeichen, A–Z/a–z/0–9/_/-) |

Listen liefern `orders`, `total`, `offset`, `limit`; Mitarbeiterlisten zusätzlich `assignees` mit ID/Name.
Listen enthalten `positionCount`, Details enthalten `positions` mit damaliger Bezeichnung, kg, Preis und
Summe. Preis auf Anfrage ist `null`. `nr` ist die stabile Vorgangskennung; `revision` steigt bei Änderungen.
Mitarbeiterdetails enthalten zusätzlich `note`, `assignee`, `history`, `kunde`, `delivery`, `deliveryError`.
Kunden erhalten diese internen Felder nie. Unberechtigte Kunden-Detailabrufe ergeben 404.

Statusübergänge: neu → in_bearbeitung oder storniert; in_bearbeitung → neu, bestaetigt oder storniert;
bestaetigt → in_bearbeitung, erledigt oder storniert. Erledigt/storniert bleiben abgeschlossen.
Notiz/Zuständigkeit können ohne Statusänderung aktualisiert werden. Ungültiger Übergang: 422;
veraltete Revision: 409. Es wird keine Bestätigungs-E-Mail beim Statuswechsel ausgelöst.

Für neue Clients ist `requestId` pro bewusster Übermittlung zu erzeugen und bei Netzfehlern mit
unveränderten Nutzdaten wiederzuverwenden. Gleicher Kunde + gleiche Kennung + gleiche Nutzdaten liefern
beim Wiederholen dieselbe Nummer mit `replayed: true`, ohne erneuten Mailversand. Geänderte Nutzdaten
unter derselben Kennung ergeben 409. Alte Clients ohne Kennung bleiben kompatibel, haben aber keinen
Wiederholungsschutz. Eine einmal erfolgreich beantwortete Bestellung darf bei einer neuen bewussten
Bestellung mit einer neuen Kennung erneut bestellt werden.

Ein wiederholter Abruf kann `delivery: neu` (Übermittlung läuft/ungeklärt), `gesendet` oder `fehler`
melden. `ok: true` bei einer Wiederholung bestätigt die Speicherung, nicht die E-Mail-Zustellung.
Die initiale fehlgeschlagene Zustellung liefert weiterhin 502; die Bestellung bleibt gespeichert und
für Mitarbeiter sichtbar. Nach Verlust einer Antwort hilft außerdem die eigene Bestellübersicht.
