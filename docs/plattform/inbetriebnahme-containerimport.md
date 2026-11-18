# Inbetriebnahme: Modul „Container-Import“ (container-import.dashboard-stafl.de)

Stand 18.11.2026. Entscheidung des Inhabers: gleich produktiv, ohne vorherige Testfreigabe. Diese Anleitung enthält keine
Adressen des Servers und keine Zugangsdaten.

**Kennzeichnung:** *getestet* = so ausgeführt und geprüft (lokal bzw. in der CI). *Abgeleitet* = aus Doku und Skripten
hergeleitet, auf dem Server und bei bunny.net nicht ausgeführt.

## 1. Was sich mit dem Release ändert

- `https://container-import.dashboard-stafl.de/` zeigt statt des 503-Platzhalters das Modul (Reiter EUDR). Die Kachel
  und der Eintrag in der Seitenleiste werden zum Verweis.
- Den Modulzugang haben die Standardrollen. **Inhalte sieht nur, wer „EUDR ansehen“ hat**, speichern kann nur, wer
  „EUDR bearbeiten“ hat. Keine Rolle hat diese Rechte von sich aus – auch sie müssen vergeben werden (Schritt 5);
  Administratoren haben sie.
- Kein Datenformat ändert sich, keine Migration. Für alle anderen Adressen ändert sich nichts.

## 2. Anders als beim Versand: kein DNS-Schritt

Der DNS-Eintrag `container-import` besteht seit 25.10.2026 und zeigt auf die bunny-Zone `stafl-dashboard-2`
(`docs/bunny-cdn.md`). Die Adresse stand bisher als Platzhalter im `Caddyfile`; der Server hält dafür bereits ein
Zertifikat (*abgeleitet*: Caddy holt Zertifikate für jede Adresse seiner Einstellung, also auch für Platzhalter – auf dem
Server nicht nachgesehen). Der A-Eintrag-Umweg aus `inbetriebnahme-versand.md` entfällt deshalb. Prüfen lässt es sich vor
dem Release: `curl -sI https://container-import.dashboard-stafl.de/` muss ohne Zertifikatsfehler mit „503“ antworten.

## 3. Ablauf

| Nr. | Schritt | Wo | Stand |
|---|---|---|---|
| 1 | **Release freigeben** (`docs/release-freigabe.md`). Caddyfile und Compose-Datei sind geändert, die Container starten neu. Bis Schritt 2 erledigt ist, meldet nur die neue Adresse bei der Anmeldung einen Fehler; alle anderen Adressen arbeiten normal. | GitHub | Ablauf wie bei jedem Release; für diesen Stand nicht ausgeführt |
| 2 | **Anmeldung (Keycloak):** `cd /opt/wochenangebot && sh deploy/anmeldung/konten.sh realm-aktualisieren` – erwartet: „angelegt: Client containerimport“, „erzeugt: OIDC_SECRET_CONTAINERIMPORT in .env“, „erzeugt: OIDC_CRYPTO_CONTAINERIMPORT in .env“, am Ende „Realm aktuell (Stand 19 …)“. Danach `docker compose up -d app-mitarbeiter`. Geheimnisse werden nie angezeigt. | Server | getestet nur in der CI (Keycloak-Prüfung); auf dem Server nicht ausgeführt |
| 3 | **Adresse prüfen:** `https://container-import.dashboard-stafl.de/` öffnen → Anmeldung → Seite „Container-Import“ mit dem Reiter EUDR. | Browser | Seite getestet (Testgruppe `containerimport`); über bunny abgeleitet |
| 4 | **Straßen und Orte auf der Karte (bunny, freiwillig):** Zone `stafl-dashboard-2` → Caching → General → **„Optimize for large object delivery“ einschalten**. Satellitenbild, Wald 2020 und Waldverlust brauchen das nicht – sie kommen direkt von den drei Kartendiensten (Abschnitt 6). Ohne die Einstellung fehlt nur die Ebene „Straßen und Orte“ aus der Kartendatei des Servers (bunny gibt deren Abschnitts-Anfragen sonst nicht weiter, Befund 04.11.2026, `docs/bunny-cdn.md` Abschnitt 6). Die Einstellung gilt für alle Adressen dieser Zone, nicht nur für den Container-Import. | bunny.net | abgeleitet, nicht getestet (in `stafl-dashboard-1` seit 04.11.2026 so in Betrieb); am 18.11.2026 im Konto nachgesehen: aus |
| 5 | **Rechte vergeben:** Verwaltung → Rollen und Rechte (Bereich „Container-Import“) oder beim Mitarbeiter als Ausnahme „erlauben“: „EUDR ansehen“, „EUDR bearbeiten“. | Verwaltung | Rechte getestet (Testgruppe `containerimport`) |

Die Kartendatei selbst lädt `sh deploy/karte-laden.sh laden herkunft` (geladen am 18.11.2026, Zoomstufe 14).

## 4. Wenn etwas nicht klappt

| Zeichen | Ursache und Abhilfe |
|---|---|
| Schritt 2: „Abbruch“ oder kein „angelegt: Client containerimport“ | Ausgabe aufbewahren, nichts von Hand in Keycloak ändern. Der Befehl ist wiederholbar. |
| Schritt 3: Anmeldung meldet einen Fehler zum Client oder zur Rücksprungadresse | Schritt 2 fehlt oder `docker compose up -d app-mitarbeiter` wurde nicht ausgeführt. |
| Schritt 3: „502“ von bunny oder Zertifikatsfehler | Der Server hat für die Adresse doch kein gültiges Zertifikat. `docker compose logs --since 15m caddy \| grep -i container-import` ansehen; Vorgehen dann wie in `inbetriebnahme-versand.md`, Abschnitt 3 und 4. |
| Seite öffnet, zeigt aber „keine Berechtigung“ | „EUDR ansehen“ fehlt (Schritt 5). |
| Karte zeigt nur Länderumrisse | Die Kartendienste antworten nicht (Netz des Arbeitsplatzes, Dienst gestört) **und** die Kartendatei des Servers kommt nicht an. Browser-Konsole ansehen: eine Meldung zur Content-Security-Policy heißt, die Adresse fehlt im `Caddyfile` (Zuordnung `csp_karten`). |
| Karte mit Satellitenbild, aber ohne die Ebene „Straßen und Orte“ | Schritt 4 fehlt, oder die Kartendatei ist nicht geladen (`ls -l daten-karte/herkunft.pmtiles`). |
| Bildauswertung fehlt im Fenster „Betrieb“ | Dienste nicht erreichbar (wie oben) oder der Betrieb ist nur ein Punkt. „Nicht möglich“ nennt den Grund. |

## 5. Rückfall

`sh /opt/wochenangebot/deploy/release-zurueck.sh` stellt den Stand vor dem Release wieder her; die Adresse ist dann wieder
Platzhalter. Stehen bleiben dürfen der Keycloak-Client `containerimport`, die neuen Zeilen in `.env` und die Einstellung bei
bunny. Erfasste Herkunftsbetriebe und Sendungen bleiben im Speicher; der alte Stand zeigt sie nicht an und ändert sie nicht.

## 6. Karte: Satellitenbild und Waldflächen (ab dem Release mit der Kartenerweiterung)

Entscheidung des Inhabers 18.11.2026: Satellitenbild und Waldflächen wie in Global Nature Watch und Whisp, Kartendaten direkt
im Browser. Dafür ist kein Schritt auf dem Server nötig – das Release genügt.

- **Was der Browser abruft:** Satellitenbild (EOX, Sentinel-2 cloudless 2016), Wald Ende 2020 (EU-Kommission/JRC),
  Waldverlust seit 2021 (Global Forest Watch). Nur auf `container-import.dashboard-stafl.de`; alle anderen Adressen der
  Plattform laden weiter nichts von fremden Servern (*getestet*: das echte `Caddyfile` mit Caddy 2.11.9 gestartet und die
  Kopfzeilen je Adresse abgerufen; in der CI prüft `tests/deploy/test_dashboard_domains.py` den Text).
- **Was die Dienste sehen:** die Adresse des Arbeitsplatzes, die Herkunft `container-import.dashboard-stafl.de` und den
  angesehenen Kartenausschnitt. Keine Anmeldedaten, keine Namen von Betrieben. Für das Verzeichnis der
  Verarbeitungstätigkeiten: drei weitere Empfänger technischer Verbindungsdaten der Mitarbeiter (EOX IT Services GmbH,
  Österreich; Europäische Kommission; World Resources Institute, USA).
- **Stand der Bilder:** Das Satellitenbild ist von 2016 – der einzige Jahrgang, den EOX Unternehmen ohne Entgelt überlässt.
  Aktuelle Jahrgänge (auch 2020 zum Vergleich) gibt es dort gegen Entgelt. Der Waldverlust reicht bis zum jüngsten Jahr,
  das der Dienst liefert (am 18.11.2026: 2025); die Karte findet es selbst.
- **Bildauswertung:** eine Schätzung, kein Nachweis. Sie trägt nichts ein und ändert kein Risikoprofil.
- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Karte zeigt dann wieder Herkunftskarte bzw. Umrisse.
