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
| In der Auswahl „Ebenen“ fehlt ein Eintrag | Dieser Dienst hat beim Öffnen der Karte nicht innerhalb von acht Sekunden geantwortet. Die Karte prüft beim nächsten Öffnen neu (Ansicht wechseln oder Seite neu laden). |
| Bildauswertung fehlt im Fenster „Betrieb“ | Walddienst oder Waldverlust nicht erreichbar (wie oben) oder der Betrieb ist nur ein Punkt. „Nicht möglich“ nennt den Grund. |

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

## 7. Whisp automatisch abfragen (ab dem Release mit der Whisp-Abfrage)

Auftrag des Inhabers 19.11.2026. Im Fenster „Betrieb“ schickt der Knopf „In Whisp prüfen“ den Umriss an Whisp (FAO) und zeigt
das Ergebnis als Vorschlag für die Gegenprüfung. Ohne Schlüssel auf dem Server gibt es den Knopf nicht – das Release allein
ändert fachlich also nichts. Weil sich die Container-Beschreibung ändert, startet dieses Release aber alle Container neu
(`deploy/freigabe-einspielen.sh`: kurze Unterbrechung aller Adressen, auch der Kundenseite) – den Zeitpunkt entsprechend wählen.

**Einrichten (einmal, Serverkonsole, Ordner `/opt/wochenangebot`):**

1. Bei Whisp anmelden (`https://whisp.openforis.org/`), auf der Kontoseite den Schlüssel erzeugen. Er wird nur einmal
   vollständig gezeigt. Ein neu erzeugter Schlüssel macht den alten sofort ungültig.
2. In `.env` eine Zeile ergänzen: `WHISP_API_KEY=<Schlüssel>` (nie ins Repository, nie in einen Chat).
3. `docker compose up -d app-mitarbeiter`
4. Prüfen: Betrieb öffnen → „In Whisp prüfen“ → nach kurzer Zeit „Ergebnis von Whisp“.

**Jährlich:** Der Schlüssel gilt 365 Tage. Danach meldet der Knopf „Whisp lehnt den Zugangsschlüssel ab“ – Schritte 1 bis 3 wiederholen.

**Abschalten:** Zeile in `.env` leeren, Schritt 3. Der Knopf verschwindet.

- **Was an Whisp geht:** nur der Umriss der Fläche, ohne Namen und Kennung, mit dem Schlüssel des Kontos. Whisp wertet mit
  Google Earth Engine aus. Für das Verzeichnis der Verarbeitungstätigkeiten: FAO (Whisp) und Google als Empfänger der Umrisse
  von Lieferantenbetrieben. Jeder Versand steht im Aktivitätsprotokoll.
- **Was zurückkommt:** Baumbestand Ende 2020, Störungen vor und nach 2020, Flächen je Datensatz, Risiko für Dauerkulturen,
  Ackerkulturen und Holz. **Für Rinder gibt Whisp noch kein eigenes Risiko aus** (Stand 19.11.2026, angekündigt).
- **Vorschlag der Seite:** „Befund“, wenn Whisp Baumbestand 2020 und eine Störung danach meldet (die Regel, die Whisp für
  Ackerkulturen nutzt). „Ohne Befund“ nur, wenn außerdem kein Datensatz eine Störung nach 2020 ab 0,5 ha zeigt – „ja“ heißt
  bei Whisp mehr als rund 10 % der Fläche, auf großen Betrieben sind das viele Hektar. In allen anderen Fällen macht die
  Seite keinen Vorschlag; das Feld „Ergebnis“ bleibt dann leer und muss gewählt werden. Störungen sind auch Brand und Ernte.
- **Nur Umrisse:** Für einen Betrieb mit nur einem Punkt gibt es den Knopf nicht (Whisp würde nur die Stelle auswerten).
- **Nichts wird von selbst eingetragen.** Erst „Gegenprüfung eintragen“ speichert.
- **Grenzen von Whisp** (am 19.11.2026 abgerufen): höchstens 100.000 ha je Fläche; die Auswertung dauert Sekunden bis Minuten.
- *Getestet* mit nachgebautem Dienst (Gruppe `containerimport_whisp`). *Am echten Dienst geprüft* nur ohne Schlüssel:
  Adressen, Antwortformat laut Beschreibung der Schnittstelle, Ablehnung ohne und mit falschem Schlüssel. **Der erste echte
  Abruf ist Schritt 4** – weicht das Ergebnis vom Erwarteten ab, bitte die Anzeige als Bildschirmfoto zurückmelden.

## 8. Container als Mittelpunkt (ab dem Release mit dem Umbau)

Entscheidung des Inhabers 19.11.2026: Im Mittelpunkt steht der Container, so wie eingekauft wird – ein Einkauf bei einem
Lieferanten mit genau einer Partienummer. Kein Schritt auf dem Server, keine Migration.

- **Begriffe:** „Sendung“ heißt jetzt „Container“, „Herkunftsbetrieb“ heißt „Farmer“. Bestehende Einträge bleiben erhalten.
- **Neue Angaben am Container:** Partienummer (Pflicht, je Container eindeutig), Aktennummer, Containernummer, Stand
  (gekauft, unterwegs, Dokumente da, angekommen). Die Auftragsnummer des Lieferanten ist keine Pflicht mehr.
- **Lieferant aus den Stammdaten:** Im Feld „Lieferant“ den Namen tippen und den Vorschlag anklicken. Die Vorschläge kommen
  aus Verwaltung → Lieferanten (Export der Warenwirtschaft). Steht der Lieferant dort noch nicht, bleibt der getippte Name
  als freier Text; die Liste zeigt dann „nicht mit den Stammdaten verknüpft“.
- **Einträge von vorher:** Sie haben noch keine Partienummer und heißen in der Liste nach ihrer Auftragsnummer. Beim nächsten
  Speichern verlangt die Seite die Partienummer; dabei auch den Lieferanten aus den Vorschlägen wählen. Archivieren geht auch
  ohne Partienummer. Ist die Bewertung schon abgeschlossen, lässt sich die Partienummer einmal nachtragen.
- **Partienummer nur einmal:** Verglichen wird ohne Rücksicht auf Groß- und Kleinschreibung, Leerzeichen und Striche
  („P-100“ und „p 100“ sind dieselbe Partie). Archivierte Container zählen mit.
- **Name des Lieferanten:** Er wird am Container mitgespeichert und bei jedem Speichern aus den Stammdaten aufgefrischt, bis
  die Bewertung abgeschlossen ist. Danach bleibt er, wie er war.
- **Wer die Vorschläge sieht:** Nur wer bearbeiten darf, bekommt die Liste der Lieferanten (Nummer und Name). Wer nur ansehen
  darf, sieht den Lieferanten am Container.
- **Nach dem Abschluss der Bewertung** lassen sich Stand, Container- und Aktennummer weiter pflegen – der Container reist
  weiter. Partienummer, Lieferant und die bewerteten Angaben bleiben, wie sie abgeschlossen wurden.
- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Vorversion liest die Container weiter (sie zeigt die
  neuen Felder nicht und nennt sie wieder „Sendung“). **Achtung:** Wer in der Vorversion einen Container speichert, dessen
  Bewertung noch offen ist, verliert dort Partienummer, Aktennummer, Stand und die Verknüpfung zum Lieferanten – die
  Vorversion schreibt nur Felder, die sie kennt. Nach einem Rückfall also offene Container nicht speichern, bis die neue
  Version wieder läuft. Abgeschlossene Container sind nicht betroffen. Ab dieser Version bleiben unbekannte Felder beim
  Speichern erhalten, sodass ein Rückfall von einem späteren Schritt auf diesen nichts mehr verliert.
- **Inzwischen umgesetzt:** Schlachthöfe unter dem Lieferanten (Abschnitt 9), Tracking der Container (Abschnitte 10 und 11),
  Farmer je Container (Abschnitt 12).
- **Geplant, je eigener Schritt:** Verbindung zum Bestand über die Partienummer, Auswertung je Lieferant.

## 9. Schlachthöfe unter dem Lieferanten (ab dem Release mit den Schlachthöfen)

Entscheidung des Inhabers 19.11.2026: Der Lieferant ist der Produzent, ihm gehören Schlachthöfe, an sie liefern die Farmer.
Kein Schritt auf dem Server, keine Migration, keine neuen Rechte.

- **Anlegen:** Ansicht „Schlachthöfe“ → „Neuer Schlachthof“: Name, Lieferant (Vorschlag der Stammdaten anklicken), Land, Ort,
  Zulassungsnummer. Der Name ist je Lieferant nur einmal vergeben.
- **Am Container:** Im Fenster „Container“ steht das Feld „Schlachthof“. Zur Wahl stehen nur die Schlachthöfe des gewählten
  Lieferanten. Wechselt der Lieferant, muss der Schlachthof neu gewählt werden.
- **Umbenennen:** Container mit offener Bewertung zeigen sofort den neuen Namen, abgeschlossene behalten den von damals.
- **Lieferant eines Schlachthofs:** Stehen schon Container daran und ist der Lieferant mit den Stammdaten verknüpft, lässt er
  sich nicht mehr wechseln. Für einen anderen Lieferanten einen eigenen Schlachthof anlegen. Solange der Lieferant freier
  Text ist, lässt er sich berichtigen oder mit den Stammdaten verknüpfen – die Container dieses Schlachthofs mit offener
  Bewertung bekommen den Lieferanten dann mit.
- **Archivieren statt löschen:** Ein archivierter Schlachthof bleibt an seinen Containern, lässt sich aber nicht neu wählen.
- **Container von vorher** haben keinen Schlachthof. Er lässt sich jederzeit eintragen, nach dem Abschluss der Bewertung einmal.
- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Vorversion zeigt die Schlachthöfe nicht, behält sie aber
  beim Speichern eines Containers (unbekannte Felder bleiben seit Abschnitt 8 erhalten). Das Dokument der Schlachthöfe bleibt
  unberührt liegen.

## 10. Reiter „Tracking“ (ab dem Release mit dem Tracking)

Auftrag des Inhabers 19.11.2026: sehen, wo ein Container ist und wann er ankommt, mit Schiffsname. Erste Stufe ohne fremde
Dienste. Kein Schritt auf dem Server, keine Migration, keine neuen Rechte (ansehen mit „EUDR ansehen“, speichern mit
„EUDR bearbeiten“).

- **Pflegen:** Reiter „Tracking“ → Container anklicken: Containernummer, Stand, Schiff, Reederei, Abgangs- und Zielhafen,
  geplante Abfahrt und Ankunft, Konnossement. Das geht auch, wenn die EUDR-Bewertung schon abgeschlossen ist.
- **Liste:** zeigt alle Container, die noch nicht angekommen sind, nach Ankunft sortiert – überfällige zuerst. „Angekommene
  anzeigen“ blendet die übrigen ein.
- **Sendungsverfolgung der Reederei:** Mit Containernummer und Reederei erscheint im Fenster ein Verweis. Er öffnet die Seite
  der Reederei in einem neuen Fenster und legt die Containernummer in die Zwischenablage. Die Adressen stehen in
  `app/api/module/containerimport/tracking.php` (`CI_REEDEREIEN`) und sind beim Bau nicht einzeln geprüft worden – stimmt
  eine nicht mehr, dort anpassen.
- **Was die Seite nicht tut:** Sie fragt weder Reederei noch Hafen ab. Ankunftszeiten ändern sich also nur, wenn jemand sie
  einträgt. Geplant: bestätigte Ankunft in Hamburg aus der öffentlichen Liste des Hafens (HVCC), später die lange Vorausschau
  über die HVCC-Schnittstelle oder einen Tracking-Dienst – jeweils erst nach Entscheidung des Inhabers.
- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Vorversion zeigt den Reiter nicht, behält die Angaben
  aber beim Speichern eines Containers.

## 11. Tracking: Ankunft in Hamburg aus der Liste des Hafens (ab dem Release mit der Hafenliste)

Zustimmung des Inhabers 19.11.2026. Kein Schritt auf dem Server, keine Einstellung, kein Schlüssel.

- **Was passiert:** Hat ein Container, der noch nicht angekommen ist, einen Schiffsnamen und als Zielhafen Hamburg, ruft der
  Server die öffentliche Seite `https://www.hafen-hamburg.de/en/all-vessels/expected-vessels/` ab – höchstens alle zwei
  Stunden, nach einem Fehlschlag frühestens nach 15 Minuten. Steht das Schiff dort, zeigt der Reiter „Tracking“ bestätigte
  Ankunft, Liegeplatz und Terminal neben der geplanten Ankunft.
- **Grenzen:** Gelesen werden die nächsten 24 Ankünfte (erste Seite der Liste) – ein Schiff erscheint also erst kurz vor der
  Ankunft, je nach Verkehr etwa einen Tag vorher. Zugeordnet wird über den Schiffsnamen – er muss stimmen – und nur bei
  Zielhafen Hamburg: Ein Container nach Rotterdam bekommt keine Hamburger Ankunft gezeigt, auch wenn sein Schiff Hamburg
  anläuft. Eine Meldung verschwindet zwölf Stunden nach der gemeldeten Ankunft. Aufgefrischt wird beim Öffnen der Seite, mit
  „Stand neu laden“, nach dem Speichern des Trackings und sonst frühestens alle 15 Minuten, sobald jemand in der Seite arbeitet –
  die Uhrzeit des Stands steht in der Hinweiszeile. Sie ist ein Hinweis: Stand und geplante
  Ankunft ändert weiter nur ein Mensch.
- **Was hinausgeht:** nur der Abruf der Seite vom Server. Keine Containernummer, kein Schiffsname, keine Angaben zu
  Mitarbeitern. Der Abruf nennt als Absender „STAFL-Plattform (Standard-Fleisch, Container-Import)“, damit der Hafen sieht,
  wer abruft.
- **Nach dem Release einmal ansehen:** Container mit einem Schiff anlegen, das gerade auf der Seite des Hafens steht (Zielhafen
  Hamburg), Reiter „Tracking“ öffnen. Unter der Kopfzeile muss „Ankünfte in Hamburg laut Hafen Hamburg (HVCC), Stand …“ stehen
  und am Container die Meldung. Steht dort „ließ sich nicht lesen“ oder „nicht erreichbar“, bitte an Claude melden.
- **Abschalten:** nicht nötig – ohne passenden Container wird nichts abgerufen. Rückfall: `sh /opt/wochenangebot/deploy/release-zurueck.sh`
  (die Vorversion kennt die Meldungen nicht; das Dokument bleibt liegen).

## 12. Farmer je Container (ab dem Release mit den Farmer-Nummern)

Auftrag des Inhabers 19.11.2026: Schlachthöfe und Farmer nur einmal anlegen, je Container die Farmer der Sendung festhalten,
eine Gesamtprüfung je Container und eine Übersicht aller Farmer. Kein Schritt auf dem Server, keine Migration, keine neuen
Rechte.

- **Zwei Nummern je Farmer:** die eigene Farmer-Nummer (F-0001, F-0002 …, fortlaufend, nie wiederverwendet) und die Nummer aus
  den Papieren des Lieferanten (z. B. SIGOR-Nummer). Die Nummer aus den Papieren gibt es je Land nur einmal; „12.345“ und
  „12 345“ gelten als dieselbe, „-“ oder „.“ gelten als keine Nummer. Die eigene Nummer ergibt sich aus der Reihenfolge, in
  der die Farmer angelegt wurden, und wird nicht gespeichert – auch bestehende Farmer haben sie sofort. Stehen beim Einlesen
  zwei neue Farmer mit derselben Nummer aus den Papieren in einer Auswahl, meldet die Vorschau den zweiten als Fehler und
  übernimmt nur den ersten.
- **Farmer einem Container zuordnen:** Fenster „Container“ → „Farmer-Nummern aus den Papieren einfügen“ (je Zeile eine
  Nummer, auch aus Excel kopiert) → „Nummern prüfen“ → Vorschau → „In den Container übernehmen“ → „Speichern“. Bekannte
  Farmer werden zugeordnet. Zu unbekannten Nummern steht am Container „Unterlagen fehlen“; sobald ein Farmer mit dieser
  Nummer angelegt wird (Bericht einlesen oder von Hand), wird er dem Container von selbst zugeordnet – nur bei offener
  Bewertung. Eine vermerkte Nummer entfernt man durch Abhaken und Speichern.
- **Gesamtprüfung:** In der Containerliste und im Fenster steht, wie viele Farmer in Ordnung sind und was fehlt (z. B.
  „1 von 14 in Ordnung · Unterlagen fehlen: 2 · Entwaldung kritisch: 1 · eigene Prüfung offen: 12“). Fehlende Unterlagen machen die Geolokalisierung im
  Risikoprofil kritisch – „Risiko vernachlässigbar“ geht dann nicht.
- **Übersicht der Farmer:** Ansicht „Farmer“ mit beiden Nummern, Ampel, Prüfstand und den Containern (Akte · Partie), dazu
  die Nummern ohne Unterlagen. Die Suche findet auch über die Nummern, die Akten- und Partienummer und den Lieferanten.
- **Akte und Partie vorn:** Listen und Überschriften nennen „Akte … · Partie …“. Beim neuen Container ist der zuletzt beim
  Lieferanten benutzte Schlachthof vorgeschlagen.
- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Vorversion liest alles weiter. Sie zeigt die eigenen
  Nummern und die vermerkten Nummern nicht; die eigene Nummer ist nicht gespeichert und nach der Rückkehr dieselbe (sie
  ergibt sich aus der Stelle des Farmers in der Liste). Vermerkte Nummern bleiben am Container. Während des Rückfalls
  Container mit „Unterlagen fehlen“ nicht abschließen: die Vorversion kennt den Vermerk nicht und hielte die Bewertung
  ohne ihn fest. In der Vorversion angelegte Farmer werden einem Container mit vermerkter Nummer erst zugeordnet, wenn
  dieser Container nach der Rückkehr das nächste Mal gespeichert wird.

## 13. Geodaten-Katalog GEOS-EUDR (ab dem Release mit dem Geodaten-Katalog)

Auftrag des Inhabers 20.11.2026: die offene Metadatenbank GEOS-EUDR des Thünen-Instituts einbauen
(`https://github.com/GEOS-EUDR-RepoHub/Metadatabase-Geodata-EUDR`). Kein Schritt auf dem Server, keine Migration, keine
neuen Rechte, kein Abruf fremder Server.

- **Was es ist:** ein Katalog veröffentlichter offener Geodatensätze zu Wald mit Hersteller, Walddefinition, ob diese zur
  Walddefinition der EUDR passt, Auflösung, Jahren, Methode, Validierung, Genauigkeit und bekannten Grenzen. Bisher ein
  Thema („Forest/Tree Cover“, Fassung v1.0, 22 Einträge FNF01 bis FNF22). Weitere Themen (Entwaldung, Degradation,
  Rohstoffe, regional, national) kündigt das Thünen-Institut an, Aktualisierung etwa vierteljährlich.
- **Wo:** Reiter EUDR → Ansicht „Geodaten-Katalog“ (Suche, je Eintrag aufklappbar). Unter der Karte, in der Bildauswertung
  und im Ergebnis von Whisp stehen kleine Verweise wie „FNF01“ (Wald 2020 der EU-Kommission, JRC) und „FNF17“ (Waldverlust,
  Hansen/Global Forest Watch); sie öffnen den Eintrag. Recht wie die übrige EUDR-Ansicht: „EUDR ansehen“ – das prüft die
  Aktion `containerimport_eudr_geodaten`. Die Datei selbst liegt im Webroot und ist wie `lib/druck-logo.jpg` auch ohne
  Anmeldung abrufbar (`/api/module/containerimport/geodatenkatalog.json`): öffentliche Metadaten unter MIT-Lizenz, nie
  Geschäftsdaten hineinschreiben. Sperren ließe sie sich nur über `app/.htaccess` (koordinationspflichtig, eigener PR).
- **Beleg in der Gegenprüfung:** Übernimmt man Bildauswertung oder Whisp in die Gegenprüfung, nennt die Bemerkung die
  Datengrundlage mit Katalog, Thema, Fassung und Kennung (z. B. „GEOS-EUDR-Katalog (Thünen-Institut)
  ForestCover_TreeExtent v1.0: FNF01, FNF17“). So belegt die Sorgfaltsprüfung, auf welchen Daten sie steht und wie genau
  diese sind. Die Bewertung und die Ampel ändern sich dadurch nicht.
- **Whisp:** Zugeordnet sind nur Felder, deren Produkt eindeutig im Katalog steht: `EUFO_2020` → FNF01, `ESA_TC_2020` →
  FNF03, `GFC_*` → FNF17, `ForTy_*` (Fassung 1) → FNF22. Whisp kann eine neuere Fassung nutzen als der Katalog beschreibt
  (Stand 11/2026: JRC GFC 2020 V4 statt v2/v3, Hansen v1.13 statt v1.11). Ohne Zuordnung: Global Forest Types (Whisp V2,
  Katalog nur v1), ESRI (Whisp 2024/2025, Katalog bis 2023), ForTy v2, TMF, RADD, GLAD.
- **Neue Fassung übernehmen** (ein Entwickler, als eigener Pull Request): die Quelle holen und das Werkzeug aufrufen. Es
  ruft selbst nichts aus dem Netz ab. Die Quelle schreibt den Dateinamen derzeit `…_GeosEDUR_…` (Tippfehler im Original,
  Stand v1.0); das Werkzeug nimmt beide Schreibweisen an.

  ```sh
  git clone --depth 1 https://github.com/GEOS-EUDR-RepoHub/Metadatabase-Geodata-EUDR /tmp/geos-eudr
  python3 werkzeuge/eudr_geodatenkatalog.py /tmp/geos-eudr/data/<Thema>_GeosEUDR_Thuenen_vX.Y.tsv \
    --commit "$(git -C /tmp/geos-eudr log -1 --format=%h)" --zitat "<Suggested Citation aus dem README>"
  cp /tmp/geos-eudr/LICENSE app/api/module/containerimport/geodatenkatalog-LIZENZ.txt
  ```

  Ein Thema wird ersetzt, andere bleiben. `--commit` ist immer Pflicht (Herkunft jeder Fassung). `--zitat` ist Pflicht für
  ein neues Thema und für jede neue Fassung; nur beim erneuten Einlesen derselben Fassung bleibt der bisherige
  Zitiervorschlag. Fehlt eines davon, bricht das Werkzeug mit einer Meldung ab. Das Werkzeug bricht ab, ohne etwas zu schreiben, wenn sich der Aufbau ändert (andere Spalten, neue
  Hauptversion v2.0, unbekannte Einstufung „EUDR forest definition conform?“, doppelte Kennung). Dann Werkzeug,
  Oberfläche und die Zuordnung zu Whisp anpassen. Danach prüfen: `python3 tests/unit/test_eudr_geodatenkatalog.py` und
  die Gruppe `containerimport_geodaten`. Beide prüfen an der echten Datei nur den Aufbau (keine feste Anzahl, keine
  Texte); die Oberfläche testet die Gruppe mit einem erfundenen Katalog. Ändern sich die Kennungen FNF01, FNF03, FNF17 oder
  FNF22, auch `KATALOG` in `eudr-whisp.js` und die Verweise in `containerimport.js` anpassen.
- **Lizenz und Zitat:** MIT, © 2026 Thünen-Institut, Juliana Freitas Beyer, Margret Köthke, Melvin Lippe. Der Lizenztext
  liegt neben dem Katalog (`app/api/module/containerimport/geodatenkatalog-LIZENZ.txt`), die Ansicht nennt Quelle, Urheber,
  Lizenz, Fassung und Zitiervorschlag: Freitas Beyer, J., Köthke, M., & Lippe, M. (2026). GEOS-EUDR: Dataset Catalog -
  Forest Metadata (Version 1.0). Zenodo. https://zenodo.org/records/20698510
- **Keine Geschäftsdaten:** der Katalog enthält nur öffentliche Metadaten über Datensätze, keine Angebote, Bestände,
  Lieferanten oder Flächen (GR-007 nicht berührt).
- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Vorversion zeigt Ansicht und Verweise nicht; schon
  eingetragene Gegenprüfungen behalten ihre Bemerkung (reiner Text).

## 14. Dokumente je Container (ab dem Release mit den Container-Dokumenten)

Auftrag des Inhabers 20.11.2026: alle Unterlagen eines Containers am Container ablegen – mehrere Dateien, meist PDF, auch
Word, Excel und E-Mails –, mit Mini-Vorschau, GoBD-konform und richtig zugeordnet. Kein Schritt auf dem Server, keine
Migration, keine neuen Rechte. Die Dateien liegen in der Dateiablage der Plattform (Bereich `containerimport`) und kommen
mit jeder Sicherung mit.

- **Wo:** Fenster „Container“ → Bereich „Dokumente“ (unter den Stammdaten). Dateien hierher ziehen oder auswählen, mehrere auf
  einmal. Erlaubt sind PDF, Word (.doc, .docx), Excel (.xls, .xlsx, .xlsm, .xlsb), OpenDocument (.odt, .ods), E-Mails
  (.eml, .msg) und Bilder (.jpg, .jpeg, .png, z. B. ein Handyfoto eines Zertifikats); der Server prüft, dass der Inhalt zur
  Endung passt. In der Liste der Container steht je Container „7 Dokumente
  · 1 fehlt“.
- **Dokumentarten:** Kaufbestätigung, Proforma-Rechnung, Handelsrechnung, Packliste, Lot-Nummernliste / Rückverfolgbarkeit,
  Gesundheitszertifikat, Echtheitszertifikat (Hilton, Angus), Quotenzertifikat (Mercosur-Kontingent), Ursprungszeugnis, B/L
  (Konnossement), Salmonellen-Zertifikat, Halal-Zertifikat, EUDR-Dokument (Sorgfaltserklärung), Versicherungsanmeldung,
  Spedition / Buchungsbestätigung, Shipment details, Kalkulation, E-Mail / Schriftverkehr, Sonstiges. Eine Datei kann mehrere
  Arten tragen (Sammel-PDF des Lieferanten mit Rechnung, Packliste, Zertifikaten und B/L). Die Art schlägt der Dateiname vor
  (z. B. „proforma“, „invoice“, „bill of lading“, „DOCS_…“, „Kalkulation“, .eml; „Hilton“ oder „Angus“ nur, wenn sonst nichts
  passt) – nur ein Vorschlag, vor dem Hochladen änderbar.
  Ohne Vorschlag muss eine Art gewählt werden.
- **Checkliste:** Kaufbestätigung, Handelsrechnung, Packliste, Lot-Nummernliste, Gesundheitszertifikat, Echtheitszertifikat,
  Ursprungszeugnis, B/L, Versicherungsanmeldung, EUDR-Dokument und Kalkulation stehen je Container als „fehlt“ oder
  „vorhanden“. Was bei einem Container nicht gebraucht wird, lässt sich als „nicht nötig“ vermerken (und wieder aufheben).
- **Rechte:** Ansehen und Herunterladen (auch der Kalkulation) und das ZIP mit „EUDR ansehen“; Hochladen, Arten ändern,
  Entfernen und die Checkliste mit „EUDR bearbeiten“ (Entscheidung des Inhabers 20.11.2026: keine Sonderregel für die Kalkulation).
- **Nachreichen:** auch an abgeschlossenen und archivierten Containern – Unterlagen kommen oft später.
- **ZIP:** „ZIP herunterladen“ liefert alle Dateien des Containers im Originalformat, je Dokumentart ein Ordner (eine
  Sammel-PDF liegt im Ordner ihrer ersten Art), entfernte Dateien unter `_entfernt/`, dazu `index.csv` mit allen Angaben je
  Datei und `checkliste.csv` mit allen Vermerken der Checkliste (Art, nötig/nicht nötig, wer, wann).

### Verfahrensdokumentation (GoBD) – Dokumente je Container

Dieser Abschnitt beschreibt das technische Verfahren. Der Inhaber ergänzt die GoBD-Verfahrensdokumentation im QM-System
um diesen Abschnitt (Zuständigkeiten, Aufbewahrungsfristen, interne Kontrollen).

| Anforderung | Umsetzung |
|---|---|
| Unveränderbarkeit | Eine abgelegte Datei wird nie überschrieben oder geändert; jede Datei bekommt eine eigene Kennung (`ci_dokument_hochladen`, `lib/dateiablage.php`). Dieselbe Datei (gleiche Prüfsumme) kann am selben Container nicht ein zweites Mal liegen. |
| Nachweis der Unverändertheit | SHA-256 der Datei wird beim Hochladen auf dem Server berechnet und mit der Prüfsumme des Browsers verglichen; sie steht in den Metadaten und in `index.csv`. |
| Wer, wann | Name und Nutzerkennung, Zeitpunkt in UTC – beim Hochladen, Ändern der Arten, Entfernen und bei jedem Vermerk der Checkliste. |
| Zuordnung | Je Datei die Kennung des Containers und ein Schnappschuss von Partie, Akte, Containernummer, Lieferant und Auftragsnummer zum Zeitpunkt des Hochladens. Spätere Änderungen am Container ändern den Schnappschuss nicht (GR-106). |
| Änderungen | Arten ändern ist ein Vermerk im Verlauf der Datei (alt, neu, wer, wann); die Datei selbst bleibt. |
| Löschen | Gibt es nicht. „Entfernen“ ist ein Vermerk mit Pflicht-Grund; die Datei bleibt in der Ablage, abrufbar über „Entfernte anzeigen“ und im ZIP unter `_entfernt/`. Nichts wird automatisch gelöscht. |
| Protokoll | Hochladen, Arten ändern, Entfernen, Checkliste und ZIP-Export stehen zusätzlich im Aktivitätsprotokoll (ohne Dateinamen und Gründe – die stehen in den Metadaten, wie im QM-System). |
| Originalformat, Lesbarkeit | Dateien bleiben im Originalformat (keine Umwandlung). Herunterladen einzeln oder als ZIP mit `index.csv` und `checkliste.csv` (Datenträgerüberlassung bei einer Betriebsprüfung); lange Dateinamen werden im ZIP nur im Stamm gekürzt, die Endung bleibt. |
| Zugriff | Nur angemeldete Mitarbeiter mit Modulzugang und „EUDR ansehen“; Auslieferung nur über die Aktionen mit Rechteprüfung, nie als Datei des Webservers. |
| Sicherung | Die Dateien liegen unter `dateien/containerimport/` und kommen mit jeder Sicherung in einen eigenen Stand (`deploy/dateien_sichern.py`; die Metadaten verweisen mit Kennung, Größe und Prüfsumme darauf). |

- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Vorversion zeigt den Bereich „Dokumente“ nicht, ändert
  aber nichts daran: Metadaten und Dateien bleiben unberührt und sind nach der Rückkehr wieder da. Das Dokument der Container
  wird von den Dokumenten nicht verändert.

## 15. Kalkulation je Container (ab dem Release mit der Kalkulation)

Auftrag des Inhabers 20.11.2026: die bisherige Excel-Kalkulation (Hilton, Nicht-Hilton, anteilig Hilton, Ursprungsländer,
Zollsätze, Mercosur-Kontingent) im Tool nachbauen und prüfen. Kein Schritt auf dem Server, keine Migration, keine neuen
Rechte: ansehen und rechnen mit „EUDR ansehen“, speichern und festschreiben mit „EUDR bearbeiten“. Neues Dokument
`containerimport-kalkulationen` (wird beim ersten Speichern angelegt).

- **Bedienung:** Reiter „Kalkulation“ → Container anklicken. Oben der Kopf (Kurs USD je € – für den Zollwert gilt der
  Zollkurs, Art. 53 UZK; Datum der (erwarteten) Zollanmeldung – maßgeblich für Satz und Stichtag, Art. 85 UZK; Seefracht in USD oder €,
  Provision €/t mit Schalter „Einkaufsprovision“, Nachlauf €, Zuschlag €/kg, Zins und Zinstage, Zahlungskosten ‰ und fix,
  imaginärer Gewinn für den Versicherungswert; Zinstage nur ganz), dann die **Teile** (z. B. je Abnehmer: Versicherungssatz inkl. Krieg,
  Rückvergütung % vom VK, WKZ €) und die **Positionen** (Teil, Artikel, R/L, Zollregime, Ursprungsland, KN-Code, Kartons,
  Brutto, Netto, Preis in USD/kg oder €/kg, Imag. EK, VK). „Anteilig Hilton“: dieselbe Position kopieren und ein anderes
  Zollregime wählen. Das Ergebnis erscheint bei jeder Eingabe – gerechnet vom Server.
- **Formeln (in Worten):** Seefracht je kg = Seefracht in € ÷ Netto aller Positionen. Versicherungswert eines Teils =
  (Warenwert des Teils + Anteil des Teils an der Seefracht nach kg) × (1 + imaginärer Gewinn); Prämie = Versicherungswert ×
  Satz des Teils. Die Prämie verteilt sich **nach Wert** auf die Positionen (Prämie ist ein Prozentsatz vom Wert): Versicherung
  je kg einer Position = Prämie des Teils × (Warenwert + Frachtanteil der Position) ÷ (Warenwert + Frachtanteil des Teils) ÷
  Netto der Position, also (Preis + Fracht je kg) × (1 + imaginärer Gewinn) × Satz. Die Summe je Teil bleibt die Prämie; die
  bisherige Excel verteilte nach kg (teure Artikel bekommen jetzt mehr Versicherung, günstige weniger). Zollwert je kg = Preis in € + Fracht je kg + Versicherung je kg – die
  Provision nur, wenn sie keine Einkaufsprovision ist (Einkaufsprovisionen gehören nicht zum Zollwert, Art. 71 Abs. 1
  Buchst. a Ziff. i UZK). Zoll je kg = Zollwert × Wertzoll + spezifischer Zoll (€/100 kg ÷ 100). Einstand je kg = Preis +
  Fracht + Versicherung + Provision + Zoll + Nebenkosten; Nebenkosten je kg = (Nachlauf + Finanzierung + Zahlungskosten) ÷
  Netto aller Positionen + Zuschlag; Finanzierung = Warenwert × Zins × Tage ÷ 360; Zahlungskosten = Warenwert × ‰ + fix.
  Je Teil und gesamt: Ist (Einstand × kg), Soll (Imag. EK × kg), VK-Wert, Rohertrag = VK − Ist, Marge vom VK, Aufschlag auf
  das Ist (das, was die Excel „% Marge“ nannte), Rohertrag je kg, Rückvergütung, WKZ, Rohgewinn. Ohne VK bei einer Position
  steht „VK fehlt“ statt einer Marge. Gerundet wird nur in der Anzeige.
- **Sätze (Stand 20.11.2026, Vorgaben des Inhabers – vor Verwendung in TARIC prüfen):** Hilton-Kontingent 20 %; für Ursprung
  AR, BR, PY, UY ab 01.05.2026 0 % (vorläufige Anwendung des Interimsabkommens EU-Mercosur,
  https://commission.europa.eu/topics/trade/eu-mercosur-trade-agreement_en); Mercosur-Kontingent Rindfleisch 7,5 % (99.000 t
  Schlachtkörperäquivalent; Anrechnung Netto × 1,3 nur bei den KN-Codes ohne Knochen 0201 30 00 und 0202 30 90, sonst
  „nicht ermittelbar“ mit Hinweis; nur AR, BR, PY, UY); Drittlandszoll KN
  0201 30 00 (frisch/gekühlt, ohne Knochen) 12,8 % + 303,4 €/100 kg und KN 0202 30 90 (gefroren, ohne Knochen) 12,8 % +
  304,1 €/100 kg (VO (EWG) Nr. 2658/87); EU-Ursprung kein Zoll; „anderer Satz“ frei mit Pflicht-Vermerk. Die Sätze stehen nur in
  `app/api/module/containerimport/kalkulation.php` (`CI_KALK_SAETZE`); ändert sich einer, dort ändern – Entwürfe rechnen
  sofort mit dem neuen Satz, festgeschriebene Fassungen nicht. Je Kalkulation lässt sich ein Satz überschreiben, nur mit
  Vermerk; ein leeres Feld heißt „Vorgabe“ (z. B. nur den Wertzoll ändern), ein Vermerk ohne Werte überschreibt nichts.
- **Prüfhinweise:** **Fehler** (Kalkulation unvollständig, nicht festschreibbar): Hilton- oder Mercosur-Kontingent für ein
  Ursprungsland, für das es nicht gilt; Mercosur-Kontingent mit Datum vor dem 01.05.2026; „EU-Ursprung“ für ein Land außerhalb
  der EU; Drittlandszoll ohne passenden KN-Code; Kurs, Datum oder Gewicht fehlt. **Warnung/Hinweis:** EU-Land in einem
  anderen Zollregime; VK fehlt; Imag. EK weicht mehr als 10 % vom Einstand ab; überschriebener Satz. Zahlen: „0.500“ wird als
  0,5 gelesen; ein Punkt vor drei Ziffern, der über die Grenze des Feldes führt (z. B. Preis „9.875“), wird abgelehnt –
  bitte Komma als Dezimalzeichen verwenden. Grenzen: Kurs bis 10, Preis, Imag. EK und VK bis 1.000 je kg. Für Mercosur-Ursprung ohne Hilton zeigt die Seite den Zoll mit und ohne
  Mercosur-Kontingent nebeneinander.
- **Fassungen (GoBD):** Eine neue Kalkulation ist ein Entwurf („vorläufig“). „Endgültig festschreiben“ (nur ohne Fehler, mit
  Rückfrage) hält die geprüfte Eingabe, das Ergebnis mit den wirksamen Sätzen, Container, wer und wann fest – danach unveränderlich. Änderungen nur noch über
  „Neue Fassung anlegen“ mit Pflicht-Grund; alle Fassungen bleiben ansehbar, gelöscht wird nichts. Anlegen, neue Fassung
  und Festschreiben stehen im Aktivitätsprotokoll.
- **Drucken und CSV:** „Drucken“ gibt Kopf, Prüfhinweise und Ergebnis im A4-Querformat aus, „CSV“ eine Datei für Excel
  (Semikolon, Dezimalkomma; erste Zeile mit Fassung und Stand, auch „mit ungespeicherten Änderungen“). Ein Excel-Export ist nicht eingebaut (die vorhandenen Arbeitsmappen-Erzeuger gehören anderen
  Modulen).
- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Vorversion zeigt den Reiter nicht und fasst das neue
  Dokument nicht an; nach der Rückkehr ist alles wieder da.

## 16. EUDR: Umrisse abgeschlossener Bewertungen in eigenen Dokumenten (ab dem Release mit KERN-3b)

Korrektur aus dem Nachtlauf 22./23.11.2026. Kein Schritt auf dem Server, keine Migration, keine neuen Rechte.

- **Was war falsch:** Jeder Abschluss einer EUDR-Bewertung kopierte die Umrisse aller Farmer ins Dokument der Container.
  Dieses Dokument liest jede Aktion des Moduls ganz. Ab rund 200 Abschlüssen (je 10 Farmer zu 200 Punkten) fiel das ganze
  Modul mit einem Speicherfehler aus (*getestet* mit erzeugten Daten).
- **Was jetzt gilt:** Die Umrisse eines Abschlusses liegen in einem eigenen Dokument
  `containerimport-eudr-schnappschuss/<Kennung>`, einmal geschrieben und nie geändert (GoBD, GR-106). Am Container stehen die
  Farmer ohne Umriss und ein Verweis mit SHA-256-Prüfsumme. Karte im Fenster „Container“ und „GeoJSON für TRACES“ lesen die
  Umrisse von dort und prüfen die Prüfsumme; passt sie nicht, verweigern sie mit einem Hinweis. Wiederöffnen löscht nichts:
  Der frühere Abschluss verweist weiter auf sein Dokument, ein neuer Abschluss legt ein neues an.
- **Bestehende Abschlüsse** behalten ihre eingebetteten Umrisse und werden genauso angezeigt und exportiert (*getestet*,
  Testgruppe `containerimport`). Sie werden nicht umgeschrieben.
- **Gemessen** (*getestet*, `memory_limit = 128M`): 200 Abschlüsse mit je 10 Farmern zu 200 Punkten brauchten vorher mehr
  als 128 MiB (Abbruch), jetzt 32 MiB; das Dokument der Container hat dann 1,9 statt 11,5 MiB. 61 Abschlüsse mit je
  4001 Punkten: 0,19 statt 5,7 MiB.
- **Sicherung:** Die neuen Dokumente kommen mit der täglichen Sicherung mit – im Dateibetrieb als Unterordner im Archiv, im
  SQLite-Betrieb in der Datenbank (*getestet* mit `deploy/sichern.sh` in einem Wegwerf-Ordner, beide Speicherarten).
- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Vorversion liest alle Container weiter und beschädigt
  nichts. Bei Abschlüssen ab diesem Release sieht sie aber keine Umrisse: Die Karte im Fenster bricht ab (TypeError in der
  Browser-Konsole), „GeoJSON für TRACES“ liefert die Farmer mit `"geometry": null` – **diese Datei während des Rückfalls
  nicht bei TRACES einreichen**. Liste, Profil
  und Druck zeigt sie wie gewohnt. Nach der Rückkehr auf dieses Release ist alles wieder da (*getestet* mit dem Stand vor der
  Korrektur gegen Daten dieses Stands).

## 17. Argentinien: Tiere laut VISEC Carne (ab dem Release mit der VISEC-Abfrage)

Auftrag des Inhabers 24.11.2026: Bei Lieferungen aus Argentinien die Daten von VISEC Carne (`https://carne.visec.com.ar`)
abrufen. VISEC ist die Plattform der argentinischen Rindfleischkette zur EUDR. Jedes Tier (Caravana = Ohrmarke) wird dort gegen
Entwaldung nach dem 31.12.2020, Schutzgebiete und Legalität geprüft. VISEC zertifiziert nicht – das Ergebnis stützt die eigene
Prüfung. Ohne Token auf dem Server gibt es den Knopf nicht. Weil sich die Container-Beschreibung ändert, startet dieses
Release alle Container neu (kurze Unterbrechung aller Adressen, auch der Kundenseite).

**So arbeitet man damit:** Im Fenster „Container“ erscheint bei Herkunftsland Argentinien der Bereich „Tiere laut VISEC“.
Dort die DTE-Nummern aus den Papieren eintragen (Documento de Tránsito Electrónico, Transport der Tiere zum Schlachthof; eine
je Zeile). „Speichern und bei VISEC abfragen“ speichert den Container und holt je DTE Tropa, Daten und den Stand jedes Tiers.
Das Risikoprofil bekommt das Kriterium „Tiere laut VISEC (Argentinien)“:

| VISEC meldet | Kriterium |
| --- | --- |
| mindestens ein Tier ungültig | kritisch – „vernachlässigbar“ ist dann beim Abschluss nicht möglich |
| DTE noch nicht abgefragt, bei VISEC unbekannt oder ohne Tiere | offen |
| Tiere noch in Prüfung (wartet, in Validierung, Nummer bei SENASA unbekannt, von VISEC nicht erfasst) | offen |
| alle Tiere aller DTE gültig | in Ordnung, mit Zahl der Tiere und Datum der Abfrage |

Container ohne DTE-Nummern haben das Kriterium nicht; für sie ändert sich nichts. Nach dem Abschluss der Bewertung wird nicht
mehr abgefragt; das Profil hält das Kriterium mit Zahlen und Datum fest.

**Einrichten (einmal, Serverkonsole, Ordner `/opt/wochenangebot`):**

1. Bei VISEC anmelden → Profil („Tu información personal“) → „Token de acceso a la API“ → „Generar token“. Ein neu erzeugter
   Token ersetzt den alten.
2. In `.env` eine Zeile ergänzen: `VISEC_API_TOKEN=<Token>` (nie ins Repository, nie in einen Chat).
3. `docker compose up -d app-mitarbeiter`
4. Prüfen: einen Container aus Argentinien öffnen, eine DTE-Nummer aus den Papieren eintragen, „Speichern und bei VISEC
   abfragen“. Das ist der erste echte Abruf – weicht die Anzeige vom Erwarteten ab, bitte ein Bildschirmfoto zurückmelden.

**Token abgelaufen:** Die Abfrage meldet „VISEC lehnt den Zugangstoken ab“ – Schritte 1 bis 3 wiederholen. Wie lange ein
Token gilt, nennt VISEC nicht.

**Abschalten:** Zeile in `.env` leeren, Schritt 3. Der Knopf verschwindet; eingetragene Nummern, Ergebnisse und das
Kriterium bleiben.

- **Was an VISEC geht:** je DTE nur die Nummer, mit dem Token des Kontos. Keine Namen, keine Containernummer. Jede Abfrage
  steht im Aktivitätsprotokoll. Für das Verzeichnis der Verarbeitungstätigkeiten: VISEC Carne (Betreiber RDI 2K, Argentinien)
  als Empfänger von DTE-Nummern.
- **Schnittstelle** (Stand 24.11.2026, Beschreibung im Profil bei VISEC unter „Consultá la documentación de la API“): es gibt
  nur die Abfrage eines DTE und einer einzelnen Caravana. Die Liste „Mis embarques“ und der GeoJSON-Download der Flächen sind
  nur in der Weboberfläche von VISEC zu haben, nicht über die Schnittstelle.
- **Gespeichert** wird je Container und DTE die jüngste Antwort (Dokument `containerimport-visec`, vertraulich). Ein Fehler
  von VISEC überschreibt nichts.
- **Grenzen:** höchstens 30 DTE je Container; je Abfrage 15 Sekunden Frist, für alle DTE zusammen 40 Sekunden – was dann
  noch fehlt, meldet die Seite („bitte erneut abfragen“).
- *Getestet* mit nachgebautem Dienst (Gruppe `containerimport_visec`). Die Antwortfelder stammen aus der Beschreibung der
  Schnittstelle bei VISEC; **ein echter Abruf ist noch nicht geprüft** (Schritt 4).
- **Rückfall:** `sh /opt/wochenangebot/deploy/release-zurueck.sh`. Die Vorversion liest alle Container weiter und behält die
  DTE-Nummern beim Speichern; sie zeigt Bereich und Kriterium nicht.
