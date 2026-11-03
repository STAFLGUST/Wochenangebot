# bunny.net vor dem Server

Stand 02.11.2026. Ziel (Entscheidung Inhaber): **Schutz und Tempo** für **alle Adressen einschließlich der Anmeldung**.
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

## 5. Grenzen und offene Punkte

- **Bunny Shield (WAF, Bot-Abwehr)** ist ein eigenes Produkt und noch nicht eingeschaltet. Später zuerst nur „Erkennen“.
  Eine Prüfseite mit JavaScript würde App und Schnittstelle stören.
- **Uploads:** bunny nennt keine Höchstgröße. Nach der Umstellung den Import der größten Datei prüfen (Schritt 5).
- **Länderangabe:** bunny schickt `CDN-RequestCountryCode`. Die Anwendung nutzt weiter ihre eigene Ländersperre mit der
  Besucher-IP.
- Die Server-IP ist aus früheren DNS-Einträgen bekannt. Deshalb ist die Sperre (Schritt 7) nötig; ohne sie ließe sich bunny umgehen.
