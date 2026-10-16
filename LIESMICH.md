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
- Datensicherung: `tar czf /root/angebot-daten-$(date +%F).tgz -C /opt/wochenangebot daten`
- IP-Sperre: derzeit ausgeschaltet. Einschalten im `Caddyfile` (zwei Zeilen `@fremd …` / `respond @fremd …` entkommentieren), erlaubte Adressen in `.env` → `ALLOWED_IPS=…`
- Bestand: im Eingabebereich unter „Bestand“ die WinAB-Bestandsliste (.xls/.xlsx) hochladen. Mengen und MHD sind nur dort sichtbar, nie auf der öffentlichen Seite. Suche „MHD“ zeigt alle Artikel mit MHD bis heute + 14 Tage.
- Stammdaten: Bezeichnung, Fleischart, Herkunft und Zustand je Artikelnummer; werden beim Excel-Import automatisch übernommen. „frisch“ steht nur im Zustand, nie in der Bezeichnung.
- Nutzer, Rollen und Passwörter verwaltet der Administrator im Eingabebereich unter „Nutzer“; wer was geändert hat, steht unter „Protokoll“.
- Sicherheit (nur Administratoren): Zwei-Faktor-Pflicht, Passwortregeln, Inaktivitäts-Abmeldung, Kontosperre, IP-Freigabe für den Eingabebereich, Ländersperre (nur Eingabebereich oder ganze Seite), aktive Sitzungen, Sperren.
- Länderdaten: ip-location-db „geo-whois-asn-country“ (CC0, gemeinfrei). Eine Fassung liegt in `app/api/geo/`; „Länderdaten aktualisieren“ im Bereich Sicherheit lädt die neueste in den Datenordner.
- IP-Freigabe oder Ländersperre hat ausgesperrt (z. B. auf Reisen): `sh /opt/wochenangebot/deploy/ip-freigabe-aus.sh` – schaltet beides aus.
- Administrator-Passwort vergessen oder Handy (Zwei-Faktor) verloren: `sh /opt/wochenangebot/deploy/passwort-zuruecksetzen.sh admin` – gibt ein neues Passwort aus, das bei der nächsten Anmeldung geändert werden muss.
