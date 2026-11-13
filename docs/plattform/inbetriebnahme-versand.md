# Inbetriebnahme: Modul „Versand“ (versand.dashboard-stafl.de)

Stand 13.11.2026. Diese Anleitung beschreibt den Tag, an dem der Release mit dem Modul „Versand“ eingespielt wird.
Sie enthält keine Adressen des Servers und keine Zugangsdaten (`<Server-IP>` ist ein Platzhalter).

**Kennzeichnung der Schritte**

- **getestet** – so ausgeführt und geprüft (lokal bzw. in der CI; wo, steht dabei).
- **abgeleitet, nicht getestet** – aus der bestehenden Doku und den Skripten hergeleitet, aber auf dem Server, bei
  Hostinger und bei bunny.net **nicht** ausgeführt. An DNS, bunny, Server und Deployment wurde für diese Anleitung
  nichts geändert.

## 1. Was sich mit dem Release ändert

- In „Angebot bearbeiten“ gibt es die Knöpfe **„Veröffentlichen“** und **„An Kunden senden“** nicht mehr. An ihrer
  Stelle steht **„Drucken“**. In der Statuszeile steht weiter, wie viele Änderungen noch nicht veröffentlicht sind.
- Veröffentlichen, Wochenangebot versenden und Sonderposten senden liegen im neuen Punkt **„Versand“** – eigene Adresse
  `https://versand.dashboard-stafl.de/`, Eintrag in der Seitenleiste über „Verwaltung“.
- Der Versand hat einen **eigenen Zugang** („Zugang zum Modul Versand“). Keine Rolle hat ihn von sich aus, nur
  Administratoren. Die bisherigen Rechte „Angebot veröffentlichen“, „Wochenangebot senden“ und „Sonderposten senden“
  bleiben, wirken aber nur noch **zusammen mit dem Zugang**.

> **Wichtig: Die Umschaltung gilt sofort mit dem Release.** Es gibt keine Übergangszeit mit den alten Knöpfen. Vom
> Einspielen des Release (Schritt 3) bis die neue Adresse fertig ist (Schritt 8) und die Zugänge vergeben sind
> (Schritt 10), **kann niemand veröffentlichen oder an Kunden senden** – auch Administratoren nicht, weil es die Seite
> nur unter der neuen Adresse gibt. Wenn alles glatt läuft, sind das etwa 20 bis 40 Minuten; hängt ein Schritt, länger.
>
> **Empfehlung: ein ruhiger Zeitpunkt.** Nicht an dem Tag und nicht in den Stunden, in denen das Wochenangebot
> veröffentlicht oder versendet werden soll. Am besten direkt nachdem das Angebot der Woche veröffentlicht und
> versendet ist – dann ist bis zur nächsten Woche Luft, falls etwas nachgearbeitet werden muss.

## 2. Vorher klären (ohne Wirkung auf den Betrieb)

1. **Wer bekommt den Zugang „Versand“?** Liste der Mitarbeiter festlegen, und je Person, ob sie veröffentlichen, senden
   oder nur ansehen soll (Abschnitt 5). Vergeben lässt sich der Zugang erst nach dem Release – vorher gibt es das Recht
   nicht.
2. **Mitarbeiter ankündigen:** ab wann die Knöpfe weg sind, wo der Versand liegt, und dass offene Fenster von „Angebot
   bearbeiten“ nach dem Release einmal neu geladen werden müssen.
3. **Ausgangslage** (Stand 13.11.2026, Angabe der Hauptsitzung, hier nicht nachgeprüft):
   - bunny.net: Der Hostname `versand.dashboard-stafl.de` ist in der Zone `stafl-dashboard-2` schon angelegt. **SSL ist
     dort noch nicht aktiviert.**
   - Hostinger (DNS): **nichts geändert** – es gibt noch keinen Eintrag `versand`.

## 3. Warum ein A-Eintrag auf den Server nötig ist (und ob er sich vermeiden lässt)

Der Server (Caddy) braucht für die neue Adresse ein eigenes Zertifikat von Let's Encrypt. Erst mit diesem Zertifikat
kann bunny.net die Adresse an den Server weiterreichen: bunny verbindet sich verschlüsselt mit dem Server und prüft
dessen Zertifikat (`docs/bunny-cdn.md`, Einstellung „Zertifikat des Servers prüfen“).

- **Wie die bestehenden Modul-Adressen ihr Zertifikat bekommen haben:** Alle (zuletzt `qs` am 30.10.2026) wurden
  freigegeben, **bevor** bunny davorstand. Ihre DNS-Einträge zeigten damals auf den Server, Caddy hat die Zertifikate
  direkt geholt. Seit der Umstellung auf bunny werden diese Zertifikate nur noch verlängert – das geht über bunny, weil
  dabei schon ein gültiges Zertifikat da ist. `versand` ist die **erste neue Adresse seit der Umstellung**; ein
  erprobtes Vorgehen dafür gibt es noch nicht.
- **Warum es nicht direkt über bunny geht** (Teil davon getestet): Für einen Namen, für den Caddy noch kein Zertifikat
  hat, lehnt Caddy die verschlüsselte Verbindung ab. *Getestet* mit dem Caddy-Programm 2.11.9 (dieselbe Fassung wie im
  Betrieb) in einer lokalen Probe: Die Adresse mit Zertifikat antwortet, die neue Adresse ohne Zertifikat bricht beim
  Verbindungsaufbau ab. bunny käme also nicht zum Server durch, und damit auch die Prüfung von Let's Encrypt nicht.
  *Abgeleitet:* dass bunny den Namen der Adresse für die Verbindung zum Server verwendet (so sind die Zonen eingestellt).
- **Lässt sich der A-Eintrag vermeiden?** Mit der heutigen Einrichtung **nein**. Es ginge nur mit einem Umbau, der
  eine eigene Entscheidung braucht: Caddy müsste das Zertifikat über einen DNS-Eintrag holen (eigenes Caddy-Image mit
  Hostinger-Erweiterung und ein Hostinger-API-Schlüssel auf dem Server, der DNS-Einträge ändern darf). Das wäre ein
  neues Geheimnis mit viel Macht auf dem Server – für eine einzelne Adresse nicht empfohlen.
- **Was der A-Eintrag bedeutet:** Solange er steht, zeigt das DNS für `versand` die Adresse des Servers. Neu ist diese
  Information nicht – die Server-Adresse ist aus früheren DNS-Einträgen bekannt (`docs/bunny-cdn.md`, Abschnitt 6), und
  genau dafür gibt es die Sperre per Schlüssel (`CDN_PFLICHT=1`) und die Netzsperre. Der Eintrag soll trotzdem **nur
  kurz** stehen (Schritte 1 bis 6, mit kurzer Gültigkeit von 300 Sekunden) und danach durch den Verweis auf bunny
  ersetzt werden. Die Sperre per Schlüssel bleibt die ganze Zeit an: Wer in dieser Zeit direkt auf den Server geht,
  bekommt „403“.

## 4. Ablauf am Release-Tag

Reihenfolge einhalten. Schritte 1 und 2 können einige Minuten vor dem Release erledigt werden; sie ändern für
Mitarbeiter und Kunden nichts.

| Nr. | Schritt | Wo | Stand |
|---|---|---|---|
| 1 | **DNS:** neuen Eintrag anlegen – Typ **A**, Name `versand`, Ziel `<Server-IP>`, TTL 300. Prüfen (nach 1–5 Minuten): `dig +short versand.dashboard-stafl.de` zeigt die Server-Adresse. Sonst nichts an der Zone ändern (kein MX, kein TXT). | Hostinger hPanel → DNS | abgeleitet, nicht getestet |
| 2 | **Netzsperre auf „beobachten“**, falls sie auf „an“ steht – sonst erreicht Let's Encrypt den Server nicht: `cd /opt/wochenangebot && sh deploy/cdn-netzsperre.sh status`, bei Modus „an“: `sh deploy/cdn-netzsperre.sh beobachten`. Die Sperre per Schlüssel (`CDN_PFLICHT=1`) bleibt an. | Hostinger-Browserkonsole (Server) | abgeleitet, nicht getestet |
| 3 | **Release freigeben:** Pull Request ist gemergt, die CI auf `main` grün; im Release-Lauf „Review deployments“ → `produktion` → „Approve and deploy“ (`docs/release-freigabe.md`). Der Server übernimmt den Stand in etwa 2 Minuten und startet dabei alle Container neu (Caddyfile und Compose-Datei sind geändert). **Ab jetzt sind die alten Knöpfe weg.** | GitHub | Ablauf wie bei jedem Release; für diesen Stand nicht ausgeführt |
| 4 | **Zertifikat des Servers prüfen:** `docker compose logs --since 15m caddy \| grep -i versand` – erwartet wird eine Zeile „certificate obtained successfully“ für `versand.dashboard-stafl.de`. Gegenprobe: `curl -sI --resolve versand.dashboard-stafl.de:443:<Server-IP> https://versand.dashboard-stafl.de/` meldet **keinen** Zertifikatsfehler (die Antwort „403“ ist hier richtig – direkter Zugriff ohne bunny). Kommt nach 5 Minuten kein Zertifikat: Schritt 1 und 2 prüfen, dann `docker compose restart caddy` (Caddy versucht es sofort neu). | Server | abgeleitet, nicht getestet (das Caddyfile mit der neuen Adresse ist getestet: gültig laut Caddy 2.11.9) |
| 5 | **Anmeldung (Keycloak):** `sh deploy/anmeldung/konten.sh realm-aktualisieren` – erwartet: „angelegt: Client versand“, „erzeugt: OIDC_SECRET_VERSAND in .env“, „erzeugt: OIDC_CRYPTO_VERSAND in .env“ und am Ende „Realm aktuell (Stand 18 …)“. Danach `docker compose up -d app-mitarbeiter`, damit die Anwendung die neuen Werte liest. Geheimnisse werden dabei nie angezeigt. | Server | Befehl und Ausgabe: getestet nur in der CI (Keycloak-Prüfung); auf dem Server nicht ausgeführt |
| 6 | **DNS umstellen:** den A-Eintrag `versand` **löschen** und sofort als **CNAME** `versand` → `stafl-dashboard-2.b-cdn.net` anlegen (TTL 300). Ein CNAME neben einem A-Eintrag ist ungültig – deshalb erst löschen. | Hostinger hPanel → DNS | abgeleitet, nicht getestet |
| 7 | **bunny:** Zone `stafl-dashboard-2` → Hostnames → `versand.dashboard-stafl.de` → **„Activate SSL“**, danach **„Force SSL“** einschalten. Bis das Zertifikat bei bunny da ist (wenige Minuten), zeigt der Browser einen Zertifikatsfehler – die Adresse nutzt zu diesem Zeitpunkt noch niemand. | bunny.net | abgeleitet, nicht getestet |
| 8 | **Adresse prüfen:** `curl -sI https://versand.dashboard-stafl.de/` → `server: BunnyCDN-…` und `stafl-cdn: erkannt`, Weiterleitung zu `/module/versand/` bzw. zur Anmeldung. Im Browser: `https://versand.dashboard-stafl.de/` öffnen → Anmeldung (Keycloak, zweiter Faktor) → Seite „Versand“ mit den zwei Schritten „Veröffentlichen“ und „An Kunden senden“. In Sicherheit → Lagebild steht als „Ihre Adresse“ die eigene, nicht die von bunny. | beliebiger Rechner | abgeleitet, nicht getestet (die Seite selbst ist getestet: Testgruppe `versand`) |
| 9 | **Netzsperre wieder „an“** (nur wenn sie vorher „an“ war): `sh deploy/cdn-netzsperre.sh an`. Das Skript prüft danach selbst über bunny und schaltet bei einem Fehler auf „beobachten“ zurück. Gegenprobe wie in `docs/bunny-cdn.md`, Schritt 7. | Server | abgeleitet, nicht getestet |
| 10 | **Zugänge vergeben** (Abschnitt 5) und **Mitarbeiter informieren:** Seite „Angebot bearbeiten“ neu laden; der Versand steht in der Seitenleiste über „Verwaltung“. | Verwaltung → Rollen und Rechte bzw. Mitarbeiter | Rechte und Oberfläche getestet (Testgruppen `versand`, `rechte`) |
| 11 | **Probe mit einem Mitarbeiter ohne Administratorrolle:** Versand öffnen, Fenster „Veröffentlichen“ ansehen (Liste der Änderungen), Fenster „Senden“ öffnen und die Vorschau der E-Mail ansehen – **ohne** zu senden, wenn kein Versand ansteht. | Browser | – |

Danach in der Doku nachtragen (kleiner eigener PR): Datum der Inbetriebnahme, was abweichend lief, und in
`docs/bunny-cdn.md` den Hostnamen `versand.` in der Zone `stafl-dashboard-2` sowie das Vorgehen für neue Adressen.

## 5. Zugänge vergeben – wer darf was

Rechte prüft immer der Server. Ein ausgeblendeter Knopf ist nie die Berechtigung.

| Hat … | kann im Versand … |
|---|---|
| Administrator | alles |
| nur „Zugang zum Modul Versand“ | die Seite öffnen: Stand, Zahl der Änderungen, Angebote der Woche, Verlauf (ohne Kundennamen) |
| Zugang + „Angebot veröffentlichen“ | veröffentlichen |
| Zugang + „Wochenangebot per E-Mail an Kunden senden“ | das Wochenangebot senden (sieht dabei Firmen und E-Mail-Adressen der Empfänger) |
| Zugang + „Sonderposten per E-Mail an Kunden senden“ | Sonderposten eines Angebots an dessen Kunden senden |
| die Rechte **ohne** Zugang | nichts davon – die Rechte wirken nur mit dem Zugang |

Die Liste der Änderungen **mit Preisen** im Fenster „Veröffentlichen“ sieht nur, wer auch Zugang zum Angebot hat.

> **Achtung bei Bearbeitern:** Die Rolle „Bearbeiter“ hat das Recht „Angebot veröffentlichen“ schon immer als Standard,
> und das bleibt so. **Wer einem Bearbeiter den Zugang „Versand“ gibt, gibt ihm damit das Veröffentlichen.** Soll ein
> Bearbeiter den Versand nur ansehen (oder nur senden), muss „Angebot veröffentlichen“ für ihn abgewählt werden – in
> seiner Rolle (Verwaltung → Rollen und Rechte) oder bei der Person als Ausnahme „verbieten“ (Verwaltung → Mitarbeiter).

Vergeben: Verwaltung → **Rollen und Rechte** (für eine ganze Rolle, Bereich „Versand“) oder Verwaltung →
**Mitarbeiter** → Person öffnen → Ausnahme „erlauben“ (für einzelne Personen). Die Änderung gilt sofort; die Person lädt
ihre Seite einmal neu.

## 6. Wenn etwas nicht klappt

| Zeichen | Ursache und Abhilfe |
|---|---|
| Schritt 4: kein Zertifikat | DNS zeigt noch nicht auf den Server (Schritt 1, `dig`), oder die Netzsperre steht noch auf „an“ (Schritt 2). Beheben, dann `docker compose restart caddy`. Let's Encrypt erlaubt je Adresse nur wenige Fehlversuche pro Stunde – nicht in schneller Folge wiederholen. |
| Schritt 5: „Abbruch“ oder kein „angelegt: Client versand“ | Ausgabe aufbewahren, nichts von Hand in Keycloak ändern. Der Befehl ist wiederholbar (ändert nichts doppelt). |
| Schritt 8: Zertifikatsfehler im Browser | bunny-Zertifikat noch nicht fertig (Schritt 7) – einige Minuten warten, in bunny den Status des Hostnamens ansehen. |
| Schritt 8: „502“/„Bad Gateway“ von bunny | Der Server hat für die Adresse noch kein Zertifikat (Schritt 4) – oder der DNS-Eintrag wurde umgestellt, bevor Schritt 4 fertig war. Rückweg: A-Eintrag wie in Schritt 1 wieder setzen, Schritt 4 abwarten, dann Schritt 6. |
| Schritt 8: Anmeldung meldet einen Fehler zum Client oder zur Rücksprungadresse | Schritt 5 fehlt oder `docker compose up -d app-mitarbeiter` wurde nicht ausgeführt. |
| Mitarbeiter sieht weiter „Veröffentlichen“ und bekommt „Dafür fehlt Ihnen der Zugang zum Bereich Versand“ | altes, noch offenes Fenster – Seite neu laden. Der Server lehnt richtig ab. |
| Mitarbeiter sieht „Versand“ nicht in der Seitenleiste | Zugang fehlt (Abschnitt 5) oder Seite nicht neu geladen. |

## 7. Rückfall

- **Vor Schritt 3** (noch kein Release): A-Eintrag `versand` löschen, Netzsperre wieder „an“. Sonst ist nichts geschehen.
- **Nach dem Release, wenn veröffentlicht werden muss und die neue Adresse nicht fertig wird:**
  `sh /opt/wochenangebot/deploy/release-zurueck.sh` stellt den Stand vor dem Release wieder her (`docs/release-freigabe.md`,
  „Notfall-Rückfall von Hand“). Die alten Knöpfe sind dann wieder da; Mitarbeiter laden ihre Seite neu. *Abgeleitet,
  nicht getestet für diesen Stand.*
- **Daten:** Der Release ändert kein Datenformat und braucht keine Migration. Entwurf, veröffentlichtes Angebot,
  Versionen, Kunden und Protokoll bleiben, wie sie sind. Ein schon vergebener Zugang „Versand“ steht dann als
  unbekanntes Recht in den Rollen; der alte Stand beachtet ihn nicht. Wird im alten Stand eine Rolle gespeichert,
  fällt der Zugang aus dieser Rolle heraus und muss nach dem nächsten Anlauf neu vergeben werden.
- **Was stehen bleiben darf:** der Keycloak-Client `versand` und die neuen Zeilen in `.env` (ohne Wirkung), der
  Hostname bei bunny. Den DNS-Eintrag `versand` nach einem Rückfall löschen oder als CNAME auf bunny lassen – nie als
  A-Eintrag auf den Server stehen lassen.
- **Netzsperre:** nach jedem Abbruch wieder `sh deploy/cdn-netzsperre.sh an` (wenn sie vorher „an“ war).

## 8. Was wo geprüft wurde

| Was | Ergebnis |
|---|---|
| Modul, Rechte, alte Aktionen nur mit Zugang, Fenster „Veröffentlichen“ und „Senden“, Verlauf, Wartung, 390 px und dunkel | getestet: Testgruppe `versand` und die betroffenen Gruppen, beide Speicherarten (Zahlen im Pull Request) |
| Caddyfile mit der neuen Adresse | getestet: `caddy validate` mit Caddy 2.11.9 (ohne und mit CDN-Einstellungen), `tests/deploy/test_dashboard_domains.py` |
| Neue Adresse ohne Zertifikat lehnt Verbindungen ab (Grund für den A-Eintrag) | getestet: lokale Probe mit Caddy 2.11.9 |
| Geheimnisse für den neuen Client (`einrichten.sh`) | getestet: `tests/deploy/test_anmeldung_einrichten.sh` |
| Keycloak: Client `versand` wird von `realm-aktualisieren` angelegt, Anmeldung und Weiterleitungen auf dem neuen Host | nur in der CI prüfbar (Keycloak-Prüfung, `deploy/anmeldung/pruefen.sh`) |
| DNS bei Hostinger, bunny (SSL, Force SSL), Zertifikat auf dem Server, Netzsperre, Release, Rückfall | abgeleitet, nicht getestet |
