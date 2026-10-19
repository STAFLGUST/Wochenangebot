# Schnittstelle für die App (iOS/Android)

Die App im Ordner `mobile/` nutzt dieselbe Schnittstelle wie die Website (`/api/?action=…`, JSON, HTTPS) und
dieselben Geschäftsregeln: Preise, Fracht, Freischaltungen und Rechte prüft nur der Server. Für die Bestellaktionen
gilt zusätzlich [Bestell-API, Antwortformat 1](bestell-api-v1.md).

## Anmeldung: gleiche Sitzungen, Kennung in der Kopfzeile

Native Apps haben keinen Browser, der Cookies verlässlich verwaltet. Deshalb trägt die App die **vorhandene**
Sitzungskennung in einer Kopfzeile statt in einem Cookie:

| Richtung | Kopfzeile | Bedeutung |
| --- | --- | --- |
| App → Server | `X-WA-Client: app` | App-Betriebsart: Sitzungskennung nur aus der Kopfzeile, Cookies werden nicht gelesen und nicht gesetzt |
| App → Server | `X-WA-Sitzung: <Kennung>` | aktuelle Kennung (fehlt vor der ersten Anfrage) |
| Server → App | `X-WA-Sitzung: <Kennung>` | aktuelle Kennung; nach der Anmeldung neu vergeben, nach dem Abmelden leer |
| App → Server | `X-CSRF-Token` | wie im Browser bei jedem POST (aus `kunde_login`/`kunde_status` bzw. `login`/`status`) |

Es ist **dieselbe Sitzung** wie im Browser (`lib/sitzung.php`): gleiche Anmeldung mit Sperren nach Fehlversuchen,
Zwei-Faktor-Code für Mitarbeiter, Abmeldung nach Inaktivität, Sitzungsregister, Beenden durch Administratoren,
Abmeldung anderer Geräte beim Passwortwechsel, Länder- und IP-Sperre. Es gibt **keinen zusätzlichen,
langlebigen Zugangsschlüssel**. Unbekannte oder ungültige Kennungen verwirft PHP (strict mode) und vergibt eine neue,
eine Sitzungsfixierung ist damit nicht möglich. Fremde Webseiten können die Kopfzeilen nicht setzen, weil der Server
keine CORS-Freigabe erteilt. Antworten mit Sitzungskennung tragen `Cache-Control: no-store`.

Die App speichert die Kennung im Schlüsselbund (iOS) bzw. Keystore (Android), nur auf diesem Gerät
(`AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY`). Nach Ablauf der Inaktivitätsfrist meldet sich der Kunde neu an – wie im
Browser. Eine längere „angemeldet bleiben“-Frist für die App wäre eine eigene Sicherheitsentscheidung des Inhabers
(z. B. widerrufbare Gerätesitzungen oder Anmeldung über den Systembrowser mit PKCE, siehe
[App-Grundlagen](app-grundlagen.md)).

In der Auswertung erscheinen Kunden-Anmeldungen aus der App mit dem Gerätetyp „App“.

## Grunddaten: `GET ?action=app_info`

Öffentlich, ohne Sitzung, `Cache-Control: no-store`. Auch im Wartungsmodus erreichbar.

```json
{ "ok": true, "apiVersion": 1, "minAppVersion": "1.0.0", "company": "Standard-Fleisch",
  "stdPublic": true, "bestellfunktion": true, "testumgebung": false,
  "wartung": null, "links": { "kontakt": "/kontakt/", "impressum": "/impressum/", "datenschutz": "/datenschutz/" } }
```

- `minAppVersion` (Konstante `APP_MIN_VERSION` in `app/api/aktionen/app.php`): ältere Apps zeigen „Bitte
  aktualisieren“. Nur erhöhen, wenn die Schnittstelle unverträglich geändert wurde – wie jede Änderung über Release.
- `wartung`: `{ message, until }` ohne Namen des Mitarbeiters.

## Von der App genutzte Aktionen

| Bereich | Aktionen |
| --- | --- |
| Kunde | `kunde_status`, `kunde_login`, `kunde_logout`, `kunde_passwort`, `offer` (`angebot=<id>`), `kunde_merkliste`, `kunde_merkliste_save`, `kunde_bestellung` (mit `requestId`), `kunde_bestellungen`, `kunde_bestellung_detail` |
| Mitarbeiter | `status`, `login`, `login_2fa`, `logout`, `bestellungen`, `bestellung`, `bestellung_save` |

Mitarbeiter mit Pflicht zum Passwortwechsel oder zur Einrichtung der Zwei-Faktor-Anmeldung erledigen das zuerst im
Eingabebereich der Website; die App meldet sie dann wieder ab und sagt das. Aktionen mit zusätzlicher
Passwortbestätigung (Verwaltung) bietet die App nicht an.

## Regeln für Änderungen an der Schnittstelle

- Antworten nur erweitern; Felder nicht umbenennen oder entfernen, solange Apps mit älterer Version im Umlauf sind.
- Unverträgliche Änderungen: neue Aktion oder `minAppVersion` erhöhen – erst nachdem die neue App in den Stores ist.
- Die App erhält **keine** Aktualisierungen am Store vorbei (kein „Over-the-Air“-Update). Neue App-Versionen gehen
  ausschließlich über App Store / Google Play; Server-Änderungen ausschließlich über den bestehenden Release.
