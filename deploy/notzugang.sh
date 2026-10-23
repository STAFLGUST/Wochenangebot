#!/bin/sh
# Notzugang zum alten Eingabebereich (angebot-stafl.de/admin/ mit eigener Anmeldung) – nur wenn die zentrale Anmeldung
# (Keycloak) gestört ist. Im Normalbetrieb ist er stillgelegt (WA_EIGENE_ANMELDUNG=aus, docker-compose.anmeldung.yml).
# Im Installationsordner auf dem Server ausführen (dort, wo .env liegt):
#
#   sh deploy/notzugang.sh status    # zeigt, ob der Notzugang offen ist
#   sh deploy/notzugang.sh an        # alten Zugang vorübergehend öffnen (Anmeldung mit den bisherigen Passwörtern)
#   sh deploy/notzugang.sh aus       # wieder schließen – sobald die zentrale Anmeldung wieder läuft
#
# Ändert nur die Zeile WA_EIGENE_ANMELDUNG in .env und erstellt die App neu (wenige Sekunden). Kundenseite unberührt.
set -eu
umask 077
ENV="$(pwd)/.env"
COMPOSE=${COMPOSE:-docker compose}
[ -f "$ENV" ] || { echo "Abbruch: $ENV nicht gefunden – im Installationsordner ausführen." >&2; exit 1; }
jetzt() { v=$(sed -n 's/^WA_EIGENE_ANMELDUNG=//p' "$ENV" | tail -1); [ "$v" = an ] && echo an || echo aus; }
case "${1:-status}" in
  status) echo "Notzugang zum alten Eingabebereich: $( [ "$(jetzt)" = an ] && echo 'OFFEN' || echo 'geschlossen (Normalbetrieb)')"; exit 0 ;;
  an|aus) soll=$1 ;;
  *) echo "Aufruf: sh deploy/notzugang.sh status|an|aus" >&2; exit 2 ;;
esac
if [ "$(jetzt)" = "$soll" ]; then
  echo "unverändert: Notzugang ist schon $soll."
  exit 0
fi
# Zeile ersetzen bzw. anhängen; Inhalt über cat zurückschreiben, damit Rechte und Besitzer von .env bleiben
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
grep -v '^WA_EIGENE_ANMELDUNG=' "$ENV" > "$tmp" || true
if [ -s "$tmp" ] && [ -n "$(tail -c1 "$tmp")" ]; then echo >> "$tmp"; fi
echo "WA_EIGENE_ANMELDUNG=$soll" >> "$tmp"
cat "$tmp" > "$ENV"
# shellcheck disable=SC2086  # COMPOSE ist bewusst ein Befehl mit Argumenten
$COMPOSE up -d app
if [ "$soll" = an ]; then
  echo "Notzugang OFFEN: https://angebot-stafl.de/admin/ (bisherige Passwörter). Danach wieder schließen: sh deploy/notzugang.sh aus"
else
  echo "Notzugang geschlossen: Mitarbeiter nur über https://dashboard-stafl.de/"
fi
