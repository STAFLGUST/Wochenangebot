#!/bin/sh
# Notfall: IP-Freigabe und Ländersperre ausschalten (z. B. wenn sich die eigene IP-Adresse geändert hat
# oder man sich auf Reisen selbst ausgesperrt hat).
# Aufruf auf dem Server:   sh /opt/wochenangebot/deploy/ip-freigabe-aus.sh
set -e
cd "$(dirname "$0")/.."
# Dienst mit Zugriff auf alle Daten: mit der Ergänzungsdatei der Anmeldung app-mitarbeiter (sieht nach der Datentrennung,
# ADR-007 Stufe 2a, auch daten-intern/), sonst app
DIENST=app
if sed -n 's/^COMPOSE_FILE=//p' .env 2>/dev/null | grep -qF deploy/anmeldung/docker-compose.anmeldung.yml; then DIENST=app-mitarbeiter; fi
${DOCKER:-docker} compose exec -T -u www-data "$DIENST" php < deploy/ip-freigabe-aus.php
echo
