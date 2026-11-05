#!/bin/sh
# Notfallmodus beenden (Modul Sicherheit), wenn das in der Oberfläche nicht mehr geht – z. B. weil die strenge
# Notfall-Firewall die eigene Adresse gesperrt hat. Nimmt die Einstellungen der Vorlage „Notfall“ zurück, soweit sie
# seit dem Auslösen unverändert sind (gleiche Funktion wie die Oberfläche); während des Notfalls geänderte Werte bleiben.
# Gesperrte Adressen bleiben gesperrt (aufheben: Sicherheit → Firewall & Sperren); die Listen „nie sperren“, die
# freigegebenen Adressen und die Ländersperre bleiben unverändert.
# Aufruf auf dem Server:   sh /opt/wochenangebot/deploy/notfall-aus.sh
# Strenge Einstellungen behalten:   sh /opt/wochenangebot/deploy/notfall-aus.sh --streng-behalten
set -e
cd "$(dirname "$0")/.."
# Dienst mit Zugriff auf alle Daten: mit der Ergänzungsdatei der Anmeldung app-mitarbeiter (sieht nach der Datentrennung,
# ADR-007 Stufe 2a, auch daten-intern/), sonst app
DIENST=app
if sed -n 's/^COMPOSE_FILE=//p' .env 2>/dev/null | grep -qF deploy/anmeldung/docker-compose.anmeldung.yml; then DIENST=app-mitarbeiter; fi
ARG=""
if [ "${1:-}" = "--streng-behalten" ]; then ARG="streng"; fi
${DOCKER:-docker} compose exec -T -u www-data -e NOTFALL_AUS="$ARG" "$DIENST" php < deploy/notfall-aus.php
echo
