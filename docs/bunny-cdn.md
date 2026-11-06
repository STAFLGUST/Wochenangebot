# bunny.net vor dem Server

Stand 03.11.2026. Ziel (Entscheidung Inhaber): **Schutz und Tempo** für **alle Adressen einschließlich der Anmeldung**.
Am Ende nimmt der Server nur noch Anfragen über bunny.net an.

bunny.net steht als Content-Delivery-Netz (CDN) zwischen Besuchern und Server. Angriffe und Lastspitzen landen zuerst
bei bunny. Skripte, Stylesheets, Schriften und Logos der Kundenseite kommen aus dem CDN. Seiten, Schnittstelle und
alles nach der Anmeldung leitet bunny unverändert an den Server weiter und speichert es nie.

## 1. Was eingerichtet ist

**bunny.net (eingerichtet am 02.11.2026, noch ohne Wirkung, weil die DNS-Einträge noch auf den Server zeigen):**

| Zone (`<name>.b-cdn.net`) | Adressen |
|---|---|
| `stafl-kunde` | angebot-stafl.de, www.angebot-stafl.de, test.angebot-stafl.de |
| `stafl-anmeldung` | login.dashboard-stafl.de |
| `stafl-dashboard-1` | dashboard-stafl.de, www., angebot., verwaltung., bestand., hr., crm., marketing., sicherheit. (.dashboard-stafl.de) |
| `stafl-dashboard-2` | controlling., leergut., rewe., qs., einkauf., container-import., test. (.dashboard-stafl.de) |

Eine Zone fasst höchstens 10 Adressen, ihre eigene `b-cdn.net`-Adresse mitgezählt. Deshalb gibt es zwei Zonen fürs
Dashboard. Neue Modul-Adressen kommen in `stafl-dashboard-2`.

Einstellungen aller Zonen:

| Einstellung | Wert | Warum |
|---|---|---|
| Origin | `https://<Server-IP>` | direkt zum Server |
| Host-Kopf weitergeben | an | Caddy erkennt die Adresse und zeigt ihr Zertifikat |
| Zertifikat des Servers prüfen | an | Verbindung bunny → Server verschlüsselt **und** geprüft |
| Cookies entfernen | **aus** | sonst keine Anmeldung möglich |
| Speicherzeit | Angaben des Servers | nur ausdrücklich „public“ wird gespeichert (Abschnitt 2) |
| Query-Strings | berücksichtigt | `?v=…` und `?action=…` sind verschiedene Inhalte |
| Smart Cache, Fehler speichern, Stale | aus | nichts speichern, was der Server nicht freigibt |
| Optimize for large object delivery | **an** in `stafl-dashboard-1` (seit 04.11.2026), sonst aus | gibt Range-Anfragen auch für nicht gespeicherte Dateien weiter – nötig für die Detailkarte (Abschnitt 6) |
| Anfragen zusammenfassen | aus | sonst könnten sich gleichzeitige Anfragen verschiedener Nutzer mischen |
| Wiederholen bei Fehler/Zeitüberschreitung | aus (nur Verbindungsaufbau) | keine doppelten Aktionen, z. B. Mails |
| Zeitlimit Antwort | 60 s | lange Importe |
| CORS-Köpfe, Optimierer, WebSockets | aus | GR-109, unveränderte Skripte (CSP), nicht gebraucht |
| TLS 1.0/1.1 | aus | nur aktuelle Verschlüsselung |
| Protokoll bei bunny | an, IP gekürzt | Fehlersuche, Datenschutz |
| Edge Rule „STAFL: Schluessel fuer den Server“ | setzt Kopf `X-Stafl-Cdn` | Wert = `CDN_SCHLUESSEL` (Schritt 3.2) |

Bewusst **nicht** gesetzt ist eine Regel, die die Speicherzeit überschreibt. Bei einem Test hat bunny damit die
Browser-Angabe der Schnittstelle in „public, max-age=0“ geändert. „no-store“ ist aber nötig, damit auf gemeinsam
genutzten Rechnern nichts im Browser liegen bleibt.

**Server (Caddyfile, Abschnitt `cdn`; in jedem Site-Block eingebunden):**

- Ohne gültigen `CDN_SCHLUESSEL` in `.env` (32–128 Buchstaben/Ziffern) ändert sich nichts.
- Mit Schlüssel gilt die Besucher-IP von bunny (`X-Real-IP`) nur, wenn der Kopf `X-Stafl-Cdn` genau den Schlüssel enthält
  und `X-Real-IP` genau eine IP-Adresse ist (IPv4 oder IPv6). Sonst gilt wie bisher die Adresse der Verbindung. Wer bunny
  umgeht, kann seine IP also nicht fälschen. bunny überschreibt einen vom Besucher mitgeschickten `X-Real-IP` (geprüft am
  02.11.2026: gefälschte Werte änderten nichts).
- Anwendung und Keycloak bekommen die Besucher-IP als `X-Forwarded-For`, den Schlüssel nie. Damit wirken
  Ländersperre, Firewall, Anmeldebremse und Protokoll weiter für den echten Besucher.
- Die Antwort enthält den Kopf `Stafl-Cdn: erkannt`, wenn Server und bunny denselben Schlüssel kennen (zur Kontrolle).
- `CDN_PFLICHT=1`: Der Server nimmt nur noch Anfragen mit dem Schlüssel an (bunny) – ausgenommen ist nur der Caddy-Container
  selbst (127.0.0.1). Auch Abrufe vom Server brauchen den Schlüssel: Über die Docker-Weiterleitung erscheinen sie – genauso
  wie Besucher über IPv6 – mit einer privaten Adresse, deshalb gibt es keine Ausnahme für private Netze. Die Prüfung nach dem
  Einspielen (`deploy/freigabe-einspielen.sh`) liest `CDN_SCHLUESSEL` aus `.env` und schickt ihn mit (nicht in der
  Prozessliste). Alles andere bekommt 403. Ohne gültigen Schlüssel bleibt die Sperre aus.
- Seiten und Schnittstelle haben „private, no-cache“. Gespeichert werden nur „public“-Dateien der Kundenseite.
- Let's Encrypt am Server: Caddy beantwortet die Prüfungen vor allen Regeln, die Zertifikate verlängern sich also auch über
  bunny (Kontrolle in Schritt 5).

Geprüft mit echtem Caddy: `tests/deploy/test_cdn.py`. Die CI prüft das Caddyfile auch mit eingeschaltetem CDN.

## 2. Was bunny speichert

| Inhalt | Kundenseite | Dashboard, Anmeldung |
|---|---|---|
| Skripte/Stylesheets mit `?v=` | 1 Jahr | nur im Browser („private“) |
| Schriften, Symbole, Logos | 1 Tag | nur im Browser |
| Keycloak-Dateien (`/resources/`) | – | wie von Keycloak angegeben |
| Seiten, Schnittstelle, Weiterleitungen, Fehler | nie | nie |

Nach einem Release muss nichts geleert werden: Neue Fassungen haben eine neue `?v=`-Adresse. Bei einem Problem mit einer
Datei: bunny → Zone → „Purge Cache“.

## 3. Umstellung – Reihenfolge

> Wichtig: Schritt 3.1 (Release mit dem Abschnitt `cdn`) muss **vor** jeder DNS-Umstellung erledigt sein. Probe vom
> 02.11.2026 über bunny ohne diesen Abschnitt: Die Schnittstelle antwortete „Der Zugriff aus Ihrem Land ist leider nicht
> möglich“. Der Server sah statt des Besuchers die Adresse des bunny-Servers. Ländersperre, Firewall und Anmeldebremse
> hätten alle Besucher gemeinsam getroffen.

1. **Release einspielen:** den PR mit dem Abschnitt `cdn` mergen und freigeben. Ohne Schlüssel ändert das nichts.
2. **Schlüssel setzen** (Hostinger-Browserkonsole):
   ```sh
   cd /opt/wochenangebot
   openssl rand -hex 32          # Ausgabe kopieren
   nano .env                     # CDN_SCHLUESSEL=<Ausgabe>   CDN_PFLICHT=0
   docker compose up -d caddy
   ```
   Denselben Wert in bunny in **allen vier Zonen** eintragen: Edge Rules → „STAFL: Schluessel fuer den Server“ → Wert
   „BITTE-ERSETZEN“ ersetzen. Der Schlüssel steht nur in `.env` und in diesen Regeln, nirgends sonst.
3. **Zertifikate bei bunny** (damit HTTPS ab der ersten Minute gilt):
   - Mit DNS-Prüfung **vor** der Umstellung, ohne Ausfall: Je Adresse liefert bunny einen TXT-Eintrag
     `_acme-challenge.<adresse>` (API `requestExternalDnsCertificate`). Diese Einträge bei Hostinger anlegen und danach
     abschließen (`completeExternalDnsCertificate`). TXT-Einträge ändern nichts am Betrieb. Nach der Umstellung (Schritt 4)
     die `_acme-challenge`-Einträge wieder löschen: bunny verlängert die Zertifikate danach selbst über HTTP (in der API
     steht je Adresse `CertificateProvisionType: 1` = HTTP-01).
   - Oder direkt nach der Umstellung einer Adresse: Zone → Hostnames → „Activate SSL“. Bis dahin gibt es für wenige Minuten
     einen Zertifikatsfehler; wegen HSTS kommt man dann nicht auf die Seite. Diesen Weg nur für Platzhalter und Test nehmen.
4. **DNS bei Hostinger umstellen** – Adresse für Adresse, die TTL vorher auf 300 s senken:

   | Eintrag | Typ | Ziel |
   |---|---|---|
   | `test.dashboard-stafl.de`, `einkauf.`, `container-import.` (zuerst: Platzhalter) | CNAME | `stafl-dashboard-2.b-cdn.net` |
   | `controlling.`, `leergut.`, `rewe.`, `qs.` | CNAME | `stafl-dashboard-2.b-cdn.net` |
   | `www.`, `angebot.`, `verwaltung.`, `bestand.`, `hr.`, `crm.`, `marketing.`, `sicherheit.` | CNAME | `stafl-dashboard-1.b-cdn.net` |
   | `dashboard-stafl.de` (Hauptdomain, `@`) | CNAME `@` (Hostinger macht daraus ALIAS) | `stafl-dashboard-1.b-cdn.net` |
   | `login.dashboard-stafl.de` | CNAME | `stafl-anmeldung.b-cdn.net` |
   | `test.angebot-stafl.de`, `www.angebot-stafl.de` | CNAME | `stafl-kunde.b-cdn.net` |
   | `angebot-stafl.de` (Hauptdomain, `@`) | CNAME `@` (ALIAS) | `stafl-kunde.b-cdn.net` |

   Den bisherigen A-Eintrag der Adresse dabei ersetzen. **MX, SPF/DKIM/DMARC und sonstige TXT-Einträge (E-Mail) nicht
   ändern.** Vorher die Zone sichern (Hostinger legt bei jeder Änderung zusätzlich eine Momentaufnahme an).
   Die Unteradressen zeigen bisher per CNAME auf die Hauptdomain – deshalb erst alle Unteradressen umstellen, die
   Hauptdomain zuletzt. Per Hostinger-API: erst den A-Eintrag löschen, dann sofort den ALIAS setzen (ein CNAME/ALIAS
   neben einem A-Eintrag ist ungültig, auch wenn die Prüfung der API ihn annimmt).
5. **Je Adresse prüfen:**
   - `curl -sI https://<adresse>/` → `server: BunnyCDN-…` und `stafl-cdn: erkannt`
   - Sicherheit → Lagebild bzw. Verwaltung → Sicherheit: „Ihre Adresse“ ist die eigene, nicht die von bunny
   - Anmeldung (Keycloak, zweiter Faktor), Kundenlogin, Bestellung, E-Mail-Versand, Import der größten Datei (Zeitlimit
     60 s), App (iOS/Android), Abmelden
   - nach 30–60 Tagen: Das Zertifikat des Servers wurde verlängert (Caddy-Protokoll oder Ablaufdatum über
     `curl -vk --resolve <adresse>:443:<Server-IP> https://<adresse>/`)
6. **Force SSL** je Adresse in bunny einschalten (Zone → Hostnames). So leitet bunny http → https um.
7. **Sperre einschalten,** wenn alle Adressen über bunny laufen und Schritt 5 gut war – und erst, wenn der Release mit der
   Prüfung nach dem Einspielen **mit Schlüssel** (PR „CDN-Härtung“) live ist; sonst scheitert die Prüfung des nächsten
   Releases und er wird automatisch zurückgesetzt. Dann in `.env` `CDN_PFLICHT=1`, danach `docker compose up -d caddy`.
   Gegenprobe von einem anderen Rechner und vom Server selbst:
   `curl -sk --resolve angebot-stafl.de:443:<Server-IP> https://angebot-stafl.de/` → 403.
8. **bunny-API-Schlüssel zurücksetzen** (Account → API → Reset), falls er für die Einrichtung weitergegeben wurde. Das
   bunny-Konto braucht eine Zwei-Faktor-Anmeldung: Wer das Konto hat, kann den gesamten Verkehr umleiten. Ebenso einen
   für die Umstellung angelegten **Hostinger-API-Token löschen** (hPanel → Profil → API): Er erlaubt DNS-Änderungen.

Hinweis: Bei der 503-Platzhalterseite setzt bunny `Cache-Control: no-cache` statt `no-store` (bunny speichert Fehlerseiten
nicht). Bei allen anderen Antworten bleibt der Kopf des Servers unverändert (geprüft am 02.11.2026).

## 4. Rückfall

- **Sofort:** Die DNS-Einträge wieder als A-Eintrag auf `<Server-IP>` setzen (TTL 300 s, wirkt in Minuten; alternativ die
  Hostinger-Momentaufnahme von vor der Umstellung wiederherstellen) und
  `CDN_PFLICHT=0` setzen, dann `docker compose up -d caddy`.
- **Abschnitt `cdn` außer Kraft:** `CDN_SCHLUESSEL=` leeren, dann `docker compose up -d caddy`. Der Server verhält sich dann wie
  vor der Umstellung.
- Keine Daten werden umgestellt, keine Migration.

## 5. Bunny Shield (Schutzschicht bei bunny)

Eingeschaltet am 03.11.2026 (Auftrag des Inhabers): Plan **Basic** (kostenlos, 25 Mio. Anfragen im Monat) in allen vier
Zonen, zunächst **nur protokollieren**.

| Einstellung | Wert | Warum |
|---|---|---|
| Lernmodus | an bis 10.11.2026 (Vorgabe von bunny: 7 Tage) | erst Fehlalarme sehen |
| WAF (Abwehr typischer Angriffe) | Profil „General“, Ausführung **Log** | bleibt auch nach dem Lernmodus „nur protokollieren“, bis jemand umstellt |
| Kopfzeilen / Inhalt der Anfrage protokollieren | aus; `Cookie`, `Authorization`, `X-Stafl-Cdn`, `X-CSRF-Token` ignoriert | keine Sitzungen, Passwörter oder den CDN-Schlüssel in den Protokollen |
| Zu große Anfrage/Antwort für die Prüfung | Log | große Importe und Exporte werden nie wegen ihrer Größe abgewiesen |
| DDoS-Abwehr | Empfindlichkeit **niedrig** | Prüfseiten mit JavaScript nur bei echten Angriffen (stören App und Schnittstelle) |
| Bot-Erkennung, Upload-Prüfung | nur protokollieren | – |

Ratenbegrenzungen (Basic: höchstens 2 je Zone, Zeitfenster 10 s, Sperre 1 min), Aktion **Log**:

| Zone | Regel | Grenze je Besucher-Adresse |
|---|---|---|
| `stafl-kunde` | `STAFLAnmeldungKunden`: `action=kunde_login`, `kunde_token_check`, `kunde_token_set`, `kunde_passwort` | 5 in 10 s |
| `stafl-kunde`, `stafl-dashboard-1`, `stafl-dashboard-2` | `STAFLSchnittstelleallgemein`: Adressen ab `/api/` | 100 in 10 s |
| `stafl-anmeldung` | `STAFLAnmeldungMitarbeiter`: POST an `/login-actions/` (Keycloak: Passwort, zweiter Faktor) | 8 in 10 s |

Die Anmeldebremse der Anwendung (Sperre nach Fehlversuchen) bleibt unverändert; die Regeln bei bunny halten Massenanfragen
schon vor dem Server auf.

**Nach dem Lernmodus** (ab 10.11.2026): bunny → Shield → Event Logs der vier Zonen ansehen. Fehlalarme (z. B. bei Importen,
der App oder der Keycloak-Anmeldung) je Regel auf „Log“ stellen oder abschalten, dann WAF und Ratenbegrenzungen auf **Block**
bzw. **Rate Limit** umstellen. Keine Prüfseite („Challenge“) für die Schnittstelle oder die Anmeldung einschalten.

**Rückfall:** In der Zone Shield → WAF ausschalten bzw. DDoS-Empfindlichkeit „Off“; Ratenbegrenzungen löschen. Am Server
ändert sich dabei nichts.

**Datenschutz:** Shield setzt nur bei einer Prüfseite oder Bot-Erkennung eigene Cookies (`bunny_shield*`). Die
Datenschutzerklärung nennt bunny.net (BunnyWay d.o.o., Slowenien) bisher nicht – Ergänzung und Vertrag zur
Auftragsverarbeitung mit bunny sind offen (Inhaber).

## 6. Grenzen und offene Punkte

- **Uploads:** bunny nennt keine Höchstgröße. Nach der Umstellung den Import der größten Datei prüfen (Schritt 5).
- **Länderangabe:** bunny schickt `CDN-RequestCountryCode`. Die Anwendung nutzt weiter ihre eigene Ländersperre mit der
  Besucher-IP.
- Die Server-IP ist aus früheren DNS-Einträgen bekannt. Deshalb ist die Sperre (Schritt 7) nötig; ohne sie ließe sich bunny umgehen.
  Die Netzsperre (Abschnitt 7) hält solche Verbindungen schon vor Caddy auf.
- **Detailkarte (CRM-Karte, Verwaltung → Auswertung):** Die Karte liest die Kartendatei `/karte/karte.pmtiles` (rund 6 GB)
  in kleinen Abschnitten (Range-Anfragen, Antwort 206). Die Datei ist nur mit Anmeldung abrufbar und wird von bunny nicht
  gespeichert („private“). Befund 04.11.2026: Über bunny kam auf die Abschnitts-Anfrage die ganze Datei zurück (Status 200
  statt 206) – auf crm. und verwaltung.; die Seiten zeigten nur die Übersichtskarte. Laut bunny gibt eine Zone
  Range-Anfragen für nicht gespeicherte Inhalte nur mit „Optimize for large object delivery“ (Caching → General) weiter.
  **Eingeschaltet am 04.11.2026 in `stafl-dashboard-1` und geprüft:** Abschnitte kommen mit 206 (auch mitten in der Datei,
  unter 0,2 s), bunny speichert nichts (jede Anfrage „MISS“), ohne Anmeldung leitet die Datei weiterhin zur Anmeldung um
  (302), CRM-Karte und Auswertung zeigen wieder die Detailkarte. Neue Kartenhosts gehören in diese Zone oder brauchen dort
  dieselbe Einstellung. Kommt trotzdem einmal die ganze Datei, bricht die Seite den Abruf sofort ab
  (`app/assets/detailkarte.js`, Hinweis in der Browser-Konsole). **Rückfall:** Einstellung ausschalten – die Seiten zeigen
  dann wieder die Übersichtskarte.

## 7. Hostinger-Firewall und Netzsperre am Server

Zwei Schichten vor Caddy, beide unabhängig von der Anwendung:

**Hostinger-Firewall** (hPanel → VPS → Firewall, Gruppe „Wochenangebot“; filtert im Netz von Hostinger, bevor etwas den
Server erreicht, alles ohne Regel wird verworfen). Seit 06.11.2026 (Auftrag des Inhabers) gibt es nur noch eine Regel:
**TCP 443 von überall**. TCP 80 und UDP 443 (HTTP/3) sind entfernt: bunny erreicht den Server nur über HTTPS (Origin
`https://<Server-IP>`), die Umleitung von http auf https und die Zertifikatsprüfungen von Let's Encrypt laufen über bunny
(Abschnitt 1). Geprüft am 06.11.2026: alle 20 Adressen antworten über bunny wie vorher. Die Hostinger-Browserkonsole ist
davon nicht betroffen. Rückweg: Regel im hPanel wieder anlegen und „Synchronisieren“ (wirkt in etwa 2 Minuten).

Eine Liste der bunny-Adressen passt nicht in die Hostinger-Firewall: bunny hat rund 590 IPv4- und 320 IPv6-Adressen, und
die Liste ändert sich. Deshalb prüft der Server selbst:

**Netzsperre am Server** (`deploy/cdn-netzsperre.sh`, nftables, ab dem Release mit diesem Skript). Port 80 und 443 nehmen
neue Verbindungen nur noch von den Edge-Servern von bunny an. Wer bunny umgeht, erreicht Caddy gar nicht erst; die Sperre per
Schlüssel (`CDN_PFLICHT=1`) bleibt die zweite Schicht.

- **Liste:** `api.bunny.net/system/edgeserverlist` (IPv4) und `…/ipv6`, geprüft (nur öffentliche Adressen, eine Antwort mit
  weniger als 100 IPv4-Adressen oder vielen ungültigen Einträgen wird verworfen) und mit der bisherigen zusammengeführt: Eine
  Adresse bleibt 14 Tage nach ihrem letzten Erscheinen. Fällt die Abfrage aus, bleibt die bisherige Liste. Abgerufen höchstens
  alle 6 Stunden (Timer `wochenangebot-netzsperre`, alle 30 Minuten; setzt die Regeln auch nach einem Neustart).
- **Regeln:** eigene Tabelle `inet stafl_netzsperre` neben den Regeln von Docker, atomar ersetzt. Gilt nur für neue
  Verbindungen über die Schnittstelle der Standardroute an Port 80/443 – über die Docker-Weiterleitung (ursprünglicher
  Zielport) und an Dienste des Hosts (Docker-Proxy, IPv6). Abrufe vom Server selbst (Healthcheck über 127.0.0.1),
  Verbindungen nach außen, andere Ports und die Hostinger-Browserkonsole bleiben unberührt. Fremde Versuche landen im
  Kernel-Protokoll (höchstens 6 je Minute, Präfix `stafl-netzsperre:`).
- **Voraussetzung:** alle Adressen über bunny und `CDN_PFLICHT=1` mit gültigem `CDN_SCHLUESSEL` – sonst bricht das Skript ab.
  Root-Dateien im Installationsordner (nie in `daten/`): `.cdn-netzsperre` (Modus), `.cdn-netzsperre-liste.json`,
  `.cdn-netzsperre-regeln`.
- Geprüft mit echtem nftables in Netz-Namensräumen (`tests/deploy/test_cdn_netzsperre.py`: Weiterleitung wie Docker, Host,
  IPv6, andere Ports) und mit Platzhaltern (`tests/deploy/test_cdn_netzsperre.sh`). Das volle Regelwerk mit der echten
  bunny-Liste (906 Adressen) nahm nft am 06.11.2026 an.

**Einschalten** (Hostinger-Browserkonsole, nach dem Release, nur mit Freigabe des Inhabers):

```sh
cd /opt/wochenangebot
command -v nft || apt-get install -y nftables     # nft-Befehl (Docker nutzt nftables bereits im Kernel)
sh deploy/cdn-netzsperre.sh beobachten           # Regeln, die nur zählen und protokollieren – nichts wird verworfen
# 1–2 Tage später:
sh deploy/cdn-netzsperre.sh status               # Liste, Zähler, fremde Adressen der letzten 24 Stunden
sh deploy/cdn-netzsperre.sh an                   # fremde Verbindungen verwerfen
```

`status` zeigt die zehn häufigsten fremden Adressen. Steht dort „inzwischen in der bunny-Liste“, war es ein Edge-Server, den
die Liste noch nicht kannte (dann wäre er im Modus „an“ abgewiesen worden). Erwartet sind nur vereinzelte Scanner. `an` ruft
danach `https://<DOMAIN>/api/?action=status` über bunny ab; scheitert das dreimal, schaltet das Skript selbst auf `beobachten`
zurück.

**Notfall und Rückweg:** `sh deploy/cdn-netzsperre.sh aus` entfernt Regeln und Timer sofort (braucht weder Netz noch `.env`).
Vor einem Rückfall auf einen Release ohne dieses Skript ebenfalls zuerst `aus` – sonst blieben die Regeln bis zum nächsten
Neustart mit einer Liste stehen, die niemand mehr aktualisiert. Ein `nft flush ruleset` (z. B. durch den Dienst `nftables`)
entfernt auch diese Tabelle; der Timer setzt sie innerhalb von 30 Minuten wieder.
