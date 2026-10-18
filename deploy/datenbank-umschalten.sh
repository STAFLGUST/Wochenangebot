#!/bin/sh
# Only after the owner released the database-capable version. Never called automatically.
set -eu
cd "$(dirname "$0")/.."
AKTION=${1:-}
case "$AKTION" in migrate|rollback) ;; *) echo "Aufruf: sh deploy/datenbank-umschalten.sh migrate|rollback"; exit 1 ;; esac
# Existing backup process must succeed before stopping the app.
sh deploy/sichern.sh --jetzt
# Confirm the actual runtime before activating a database.
docker compose exec -T app php -r 'exit(in_array("sqlite", PDO::getAvailableDrivers(), true) ? 0 : 1);'
docker compose stop app
# On any failure leave the app stopped: operator can inspect; do not serve partially exported files.
python3 deploy/datenbank.py "$AKTION" daten --offline
chown 33:33 daten/.storage.lock
if [ "$AKTION" = migrate ]; then
  chown -R 33:33 daten/.sqlite
  chmod 700 daten/.sqlite
  chmod 600 daten/.sqlite/store.sqlite
else
  find daten -name '*.php' -exec chown 33:33 {} +
fi
docker compose start app
echo "Speicher umgeschaltet. Anmeldung, Kundenangebot, Entwurf und Bestellwunsch jetzt prüfen."
