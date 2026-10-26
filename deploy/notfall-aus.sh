#!/bin/sh
# Notfallmodus beenden (Modul Sicherheit), wenn das in der Oberfläche nicht mehr geht – z. B. weil die strenge
# Notfall-Firewall die eigene Adresse gesperrt hat. Stellt die vor dem Notfall gesicherten Sicherheits- und
# Firewall-Einstellungen wieder her. Gesperrte Adressen bleiben gesperrt (aufheben: Sicherheit → Firewall & Sperren).
# Aufruf auf dem Server:   sh /opt/wochenangebot/deploy/notfall-aus.sh
# Strenge Einstellungen behalten:   sh /opt/wochenangebot/deploy/notfall-aus.sh --streng-behalten
set -e
cd "$(dirname "$0")/.."
ARG=""
if [ "${1:-}" = "--streng-behalten" ]; then ARG="streng"; fi
docker compose exec -T -u www-data -e NOTFALL_AUS="$ARG" app php < deploy/notfall-aus.php
echo
