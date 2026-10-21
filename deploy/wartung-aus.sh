#!/bin/sh
# Notfall: alle Wartungen beenden (Angebotsseite und alle Bereiche), z. B. wenn eine Wartung die Arbeit blockiert.
# Aufruf auf dem Server:   sh /opt/wochenangebot/deploy/wartung-aus.sh
set -e
cd "$(dirname "$0")/.."
docker compose exec -T -u www-data app php < deploy/wartung-aus.php
echo
