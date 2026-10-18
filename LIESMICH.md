# Wochenangebot – angebot-stafl.de

- `app/` – Website, Eingabebereich (`/admin/`) und PHP-API
- `Caddyfile`, `docker-compose.yml` – Webserver mit automatischem HTTPS und IP-Freigabe
- `deploy/` – automatische Aktualisierung auf dem Server

Auf dem Server (`/opt/wochenangebot`) liegen zusätzlich, **nicht im Repository**:
- `.env` – Domain und freigegebene IP-Adressen (Vorlage: `.env.example`)
- `daten/` – veröffentlichtes Angebot, Entwurf, Versionen, Preisverlauf (`historie/`), Nutzer (`nutzer.php`), Protokoll (`protokoll/`), Bestand (`bestand.php`, nur intern), Stammdaten (`stammdaten.php`)

**Preisverlauf:** Eingabebereich → „Preisverlauf“. Jede Veröffentlichung wird automatisch als Woche gespeichert; ältere Angebotslisten lassen sich dort gesammelt hochladen.

Neue Versionen in `main` werden vom Server innerhalb von 2 Minuten automatisch übernommen.

Nützlich auf dem Server:
- Protokoll der Aktualisierung: `journalctl -u wochenangebot-update -n 20`
- Status: `cd /opt/wochenangebot && docker compose ps`
- Datensicherung: läuft automatisch täglich (über die Aktualisierung) nach `/opt/wochenangebot/sicherungen/`, die letzten 30 Stände; jede Sicherung wird nach dem Erstellen probeweise entpackt und geprüft. Status im Eingabebereich unter „Sicherheit“. Sofort sichern: `sh deploy/sichern.sh --jetzt`. Wichtig: Die Sicherungen liegen auf demselben Server – zusätzlich die VPS-Sicherung bei Hostinger aktivieren oder die Dateien regelmäßig woanders ablegen.
- Wiederherstellen (Beispiel): `cd /opt/wochenangebot && docker compose stop app && mv daten daten-alt && mkdir daten && tar xzf sicherungen/daten-JJJJ-MM-TT_HHMMSS.tar.gz -C daten && chown -R 33:33 daten && docker compose start app`
- Ersteinrichtung im Browser ist auf dem Server gesperrt (Schutz, falls der Datenordner einmal leer oder defekt ist). Neuen Administrator anlegen: `sh deploy/passwort-zuruecksetzen.sh admin --neu`
- IP-Sperre: derzeit ausgeschaltet. Einschalten im `Caddyfile` (zwei Zeilen `@fremd …` / `respond @fremd …` entkommentieren), erlaubte Adressen in `.env` → `ALLOWED_IPS=…`
- Bestand: im Eingabebereich unter „Bestand“ die WinAB-Bestandsliste (.xls/.xlsx) hochladen. Mengen und MHD sind nur dort sichtbar, nie auf der öffentlichen Seite. Suche „MHD“ zeigt alle Artikel mit MHD bis heute + 14 Tage.
- Mehrere Angebote: Neben dem öffentlichen Wochenangebot gibt es Kundenangebote (z. B. Edeka) mit eigenen Preisen je Artikel. Im Editor über „Preise für …“ umschalten; „Angebote verwalten“ legt neue an. Kundenangebote sind nur nach Anmeldung sichtbar (`/?angebot=<kennung>`), nie auf der öffentlichen Seite.
- Kunden (nur Administratoren, Bereich „Kunden“): Stammdaten (Firma, Kundennummer, Ansprechpartner, Adresse, E-Mail, Telefon, Notiz), freigeschaltete Angebote und Zugang (Benutzerkennung + Startpasswort, das bei der ersten Anmeldung geändert werden muss). Kunden melden sich auf der Angebotsseite über „Kunden-Login“ an und sehen nur ihre freigeschalteten Angebote; den Eingabebereich erreichen sie nie. Die Merkliste eines angemeldeten Kunden wird in seinem Kundenkonto gespeichert und ist auf allen Geräten gleich (beim ersten Anmelden wird eine im Browser angelegte Merkliste übernommen); ohne Anmeldung bleibt sie wie bisher im Browser.
- Bestellwunsch (einschalten unter Verwaltung → E-Mail → „Bestellwünsche aus dem Portal“, dort auch die Empfängeradressen): angemeldete Kunden geben in ihrem Angebot Mengen in kg ein, prüfen den Bestellwunsch (Wunschtermin, Referenz, Bemerkung) und senden ihn. Die E-Mail an die eingestellten Adressen enthält Kundendaten und alle Positionen mit den Preisen des Kunden (vom Server aus dem veröffentlichten Angebot berechnet); „Antworten“ geht direkt an den Kunden, der Kunde erhält auf Wunsch eine Eingangsbestätigung. Nummern im Format B-JJJJ-0001; jeder Bestellwunsch steht im Protokoll. Unter „Angebote verwalten“ kann ein Administrator festlegen, dass auch das Wochenangebot nur noch für angemeldete Kunden sichtbar ist.
- E-Mail an Kunden (Bereich „Kunden“): „Wochenangebot versenden“ schickt jedem ausgewählten Kunden eine eigene E-Mail mit Links zu seinen Angeboten (keine Preise in der E-Mail, Schutz vor doppeltem Versand je Kalenderwoche). Neukunden erhalten statt eines Startpassworts eine Einladung mit Einmal-Link (7 Tage gültig), über den sie ihr Passwort selbst festlegen; „Link zum Passwort-Zurücksetzen“ (2 Tage gültig) und „Angebotslink senden“ gibt es je Kunde. Jede Angebotsmail enthält „Vom Wochenangebot abmelden“ (dazu Ein-Klick-Abmeldung im E-Mail-Programm): der Kunde bestätigt auf der Angebotsseite, erhält danach keine Angebotsmails mehr (Einladungen/Passwort-Links weiterhin), die E-Mail-Adresse bleibt in den Stammdaten; wir erhalten einen Hinweis an die Antwortadresse, und in der Kundenliste steht „abgemeldet“. Versand über ein vorhandenes Postfach (SMTP). Einrichtung im Eingabebereich unter Verwaltung → „E-Mail“ (Vorlagen für Hostinger und IONOS; das Passwort wird verschlüsselt gespeichert, nie angezeigt und nach einer Wiederherstellung auf neuem Server neu abgefragt), danach eine Testmail senden. Alternativ die `MAIL_…`-Werte aus `.env.example` in `.env` auf dem Server – im Eingabebereich gespeicherte Werte haben Vorrang.
- Stammdaten: Bezeichnung, Fleischart, Herkunft und Zustand je Artikelnummer; werden beim Excel-Import automatisch übernommen. „frisch“ steht nur im Zustand, nie in der Bezeichnung.
- Nutzer, Rollen und Passwörter verwaltet der Administrator im Eingabebereich unter „Nutzer“; wer was geändert hat, steht unter „Protokoll“.
- Sicherheit (nur Administratoren): Zwei-Faktor-Pflicht, Passwortregeln, Inaktivitäts-Abmeldung, Kontosperre, IP-Freigabe für den Eingabebereich, Ländersperre (nur Eingabebereich oder ganze Seite), aktive Sitzungen, Sperren.
- Länderdaten: ip-location-db „geo-whois-asn-country“ (CC0, gemeinfrei). Eine Fassung liegt in `app/api/geo/`; „Länderdaten aktualisieren“ im Bereich Sicherheit lädt die neueste in den Datenordner.
- IP-Freigabe oder Ländersperre hat ausgesperrt (z. B. auf Reisen): `sh /opt/wochenangebot/deploy/ip-freigabe-aus.sh` – schaltet beides aus.
- Administrator-Passwort vergessen oder Handy (Zwei-Faktor) verloren: `sh /opt/wochenangebot/deploy/passwort-zuruecksetzen.sh admin` – gibt ein neues Passwort aus, das bei der nächsten Anmeldung geändert werden muss.
