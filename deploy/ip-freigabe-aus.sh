#!/bin/sh
# Notfall: IP-Freigabe des Eingabebereichs ausschalten (z. B. wenn sich die eigene IP-Adresse geändert hat).
# Aufruf auf dem Server:   sh /opt/wochenangebot/deploy/ip-freigabe-aus.sh
set -e
cd "$(dirname "$0")/.."
docker compose exec -T app php < deploy/ip-freigabe-aus.php
echo
