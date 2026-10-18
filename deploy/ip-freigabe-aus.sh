#!/bin/sh
# Notfall: IP-Freigabe und Ländersperre ausschalten (z. B. wenn sich die eigene IP-Adresse geändert hat
# oder man sich auf Reisen selbst ausgesperrt hat).
# Aufruf auf dem Server:   sh /opt/wochenangebot/deploy/ip-freigabe-aus.sh
set -e
cd "$(dirname "$0")/.."
docker compose exec -T -u www-data app php < deploy/ip-freigabe-aus.php
echo
