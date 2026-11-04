#!/bin/sh
# Notfall: Passwort eines Nutzers zurücksetzen (z. B. wenn der Administrator sein Passwort vergessen hat).
# Aufruf auf dem Server:   sh /opt/wochenangebot/deploy/passwort-zuruecksetzen.sh admin
# Der Zugang wird wieder aktiviert und entsperrt, die Zwei-Faktor-Anmeldung (auch Passkeys) zurückgesetzt;
# das neue Passwort muss bei der nächsten Anmeldung geändert werden.
# Neuen Administrator anlegen (z. B. nach Datenverlust):  sh deploy/passwort-zuruecksetzen.sh admin --neu
set -e
cd "$(dirname "$0")/.."
# Dienst mit Zugriff auf alle Daten: mit der Ergänzungsdatei der Anmeldung app-mitarbeiter (sieht nach der Datentrennung,
# ADR-007 Stufe 2a, auch daten-intern/), sonst app
DIENST=app
if sed -n 's/^COMPOSE_FILE=//p' .env 2>/dev/null | grep -qF deploy/anmeldung/docker-compose.anmeldung.yml; then DIENST=app-mitarbeiter; fi
NUTZER="${1:-admin}"
PW=$(LC_ALL=C tr -dc 'A-HJ-NP-Za-km-z2-9' </dev/urandom | head -c 14)
${DOCKER:-docker} compose exec -T -u www-data "$DIENST" php -- "$NUTZER" "$PW" ${2:-} < deploy/passwort-zuruecksetzen.php
echo
echo "Neues Passwort für \"$NUTZER\": $PW"
echo "Bitte anmelden und dann ein eigenes Passwort festlegen."
