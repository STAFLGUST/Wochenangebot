#!/bin/sh
# Notfall: alle Wartungen beenden (Angebotsseite und alle Bereiche), z. B. wenn eine Wartung die Arbeit blockiert.
# Aufruf auf dem Server:   sh /opt/wochenangebot/deploy/wartung-aus.sh
set -e
cd "$(dirname "$0")/.."
# Dienst mit Zugriff auf alle Daten: mit der Ergänzungsdatei der Anmeldung app-mitarbeiter (sieht nach der Datentrennung,
# ADR-007 Stufe 2a, auch daten-intern/), sonst app
DIENST=app
if sed -n 's/^COMPOSE_FILE=//p' .env 2>/dev/null | grep -qF deploy/anmeldung/docker-compose.anmeldung.yml; then DIENST=app-mitarbeiter; fi
${DOCKER:-docker} compose exec -T -u www-data "$DIENST" php < deploy/wartung-aus.php
echo
