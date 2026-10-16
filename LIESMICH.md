# Wochenangebot – angebot-stafl.de

- `app/` – Website, Eingabebereich (`/admin/`) und PHP-API
- `Caddyfile`, `docker-compose.yml` – Webserver mit automatischem HTTPS und IP-Freigabe
- `deploy/` – automatische Aktualisierung auf dem Server

Auf dem Server (`/opt/wochenangebot`) liegen zusätzlich, **nicht im Repository**:
- `.env` – Domain und freigegebene IP-Adressen (Vorlage: `.env.example`)
- `daten/` – veröffentlichtes Angebot, Entwurf, Versionen, Preisverlauf (`historie/`), Nutzer (`nutzer.php`), Protokoll (`protokoll/`)

**Preisverlauf:** Eingabebereich → „Preisverlauf“. Jede Veröffentlichung wird automatisch als Woche gespeichert; ältere Angebotslisten lassen sich dort gesammelt hochladen.

Neue Versionen in `main` werden vom Server innerhalb von 2 Minuten automatisch übernommen.

Nützlich auf dem Server:
- Protokoll der Aktualisierung: `journalctl -u wochenangebot-update -n 20`
- Status: `cd /opt/wochenangebot && docker compose ps`
- Datensicherung: `tar czf /root/angebot-daten-$(date +%F).tgz -C /opt/wochenangebot daten`
- IP-Freigabe ändern: `.env` → `ALLOWED_IPS=…`, danach `docker compose up -d --force-recreate caddy`
- Nutzer, Rollen und Passwörter verwaltet der Administrator im Eingabebereich unter „Nutzer“; wer was geändert hat, steht unter „Protokoll“.
- Administrator-Passwort vergessen: `sh /opt/wochenangebot/deploy/passwort-zuruecksetzen.sh admin` – gibt ein neues Passwort aus, das bei der nächsten Anmeldung geändert werden muss.
