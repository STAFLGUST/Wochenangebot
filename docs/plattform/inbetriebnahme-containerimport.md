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
