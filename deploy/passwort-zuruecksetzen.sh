#!/bin/sh
# Notfall: Passwort eines Nutzers zurücksetzen (z. B. wenn der Administrator sein Passwort vergessen hat).
# Aufruf auf dem Server:   sh /opt/wochenangebot/deploy/passwort-zuruecksetzen.sh admin
# Der Zugang wird dabei wieder aktiviert; das neue Passwort muss bei der nächsten Anmeldung geändert werden.
set -e
cd "$(dirname "$0")/.."
NUTZER="${1:-admin}"
PW=$(LC_ALL=C tr -dc 'A-HJ-NP-Za-km-z2-9' </dev/urandom | head -c 14)
docker compose exec -T app php -- "$NUTZER" "$PW" < deploy/passwort-zuruecksetzen.php
echo
echo "Neues Passwort für \"$NUTZER\": $PW"
echo "Bitte anmelden und dann ein eigenes Passwort festlegen."
