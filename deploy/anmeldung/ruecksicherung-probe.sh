#!/bin/sh
# Rücksicherung der Keycloak-Datenbank üben – ohne Eingriff in den Betrieb (Schritt 7 der Inbetriebnahme).
# Spielt eine Sicherung in eine Probedatenbank ein, zählt die Konten und löscht die Probedatenbank wieder.
#
#   sh deploy/anmeldung/ruecksicherung-probe.sh                         # neueste sicherungen/anmeldung-*.dump
#   sh deploy/anmeldung/ruecksicherung-probe.sh sicherungen/anmeldung-….dump
#
# Im Installationsordner ausführen. Das Datenbankpasswort kommt aus der Umgebung des Containers (nie Befehlszeile).
set -eu
KC_COMPOSE=${WA_KC_COMPOSE:-docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml}
DATEI=${1:-$(ls -1t sicherungen/anmeldung-*.dump 2>/dev/null | head -1)}
[ -n "$DATEI" ] && [ -f "$DATEI" ] || { echo "Abbruch: keine Sicherung gefunden (zuerst: sh deploy/sichern.sh --jetzt)." >&2; exit 1; }

im_container() { # im_container '<Befehl mit $PG…>' – läuft in keycloak-db mit Passwort aus POSTGRES_PASSWORD
  # shellcheck disable=SC2086  # KC_COMPOSE ist bewusst ein Befehl mit Argumenten
  $KC_COMPOSE exec -T keycloak-db sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\"; export PGPASSWORD; $1"
}
im_container 'dropdb -U keycloak --if-exists ruecksicherung_probe && createdb -U keycloak ruecksicherung_probe'
trap 'im_container "dropdb -U keycloak --if-exists ruecksicherung_probe" >/dev/null 2>&1 || true' EXIT
im_container 'pg_restore -U keycloak -d ruecksicherung_probe --no-owner --exit-on-error' < "$DATEI"
KONTEN=$(im_container 'psql -U keycloak -d ruecksicherung_probe -tAc "SELECT count(*) FROM user_entity"' | tr -d '[:space:]')
case "$KONTEN" in ''|*[!0-9]*) echo "Rücksicherung fehlgeschlagen: Konten nicht lesbar." >&2; exit 1 ;; esac
[ "$KONTEN" -ge 1 ] || { echo "Rücksicherung fehlgeschlagen: keine Konten in der Sicherung." >&2; exit 1; }
echo "Rücksicherung geprüft: $(basename "$DATEI") – $KONTEN Konten (inkl. Verwaltungskonto); Probedatenbank wieder gelöscht."
