#!/bin/sh
# Notzugang zum alten Eingabebereich (eigene Anmeldung mit den bisherigen Passwörtern) – nur wenn die zentrale Anmeldung
# (Keycloak) gestört ist. Seit ADR-007 Regel 6 nur noch über einen SSH-Tunnel, nie mehr auf angebot-stafl.de/admin/.
# Im Installationsordner auf dem Server ausführen (dort, wo .env liegt):
#
#   sh deploy/notzugang.sh status    # zeigt, ob der Notzugang offen ist, und wie man ihn erreicht
#   sh deploy/notzugang.sh an        # Notzugang vorübergehend öffnen
#   sh deploy/notzugang.sh aus       # wieder schließen – sobald die zentrale Anmeldung wieder läuft
#
# Erreichbar ist er nur auf 127.0.0.1 des Servers (Container app-mitarbeiter, eigener Host auf Port 8090, veröffentlicht als
# 127.0.0.1:NOTZUGANG_PORT, Standard 8190). Vom eigenen Rechner:
#   ssh -L 8190:127.0.0.1:8190 <benutzer>@<server>     und dann im Browser   http://localhost:8190/admin/
#
# Ändert nur die Zeile WA_NOTZUGANG in .env und erstellt den Container app-mitarbeiter neu (wenige Sekunden; Mitarbeiter
# melden sich danach über Keycloak ohne Passworteingabe wieder an, solange ihre Anmeldung dort gilt). Die Kundenseite (app)
# bleibt unverändert. Der Notzugang arbeitet ohne Keycloak: Konten der zentralen Anmeldung lassen sich darin nicht verwalten.
# Die frühere Zeile WA_EIGENE_ANMELDUNG (Notzugang auf der Kundenseite bis 04.11.2026) entfernt das Skript beim Umschalten.
set -eu
umask 077
ENV="$(pwd)/.env"
COMPOSE=${COMPOSE:-docker compose}
[ -f "$ENV" ] || { echo "Abbruch: $ENV nicht gefunden – im Installationsordner ausführen." >&2; exit 1; }
wert() { sed -n "s/^$1=//p" "$ENV" | tail -1; }
jetzt() { [ "$(wert WA_NOTZUGANG)" = an ] && echo an || echo aus; }
port() { p=$(wert NOTZUGANG_PORT); case "$p" in ''|*[!0-9]*) echo 8190 ;; *) echo "$p" ;; esac; }
weg() {
  echo "  Erreichbar nur über einen SSH-Tunnel vom eigenen Rechner:"
  echo "    ssh -L $(port):127.0.0.1:$(port) <benutzer>@<server>"
  echo "  dann im Browser: http://localhost:$(port)/admin/ (bisherige Passwörter der Anwendung)"
}
case "${1:-status}" in
  status)
    if [ "$(jetzt)" = an ]; then echo "Notzugang zum alten Eingabebereich: OFFEN"; weg; echo "  Schließen: sh deploy/notzugang.sh aus"
    else echo "Notzugang zum alten Eingabebereich: geschlossen (Normalbetrieb)"; fi
    exit 0 ;;
  an|aus) soll=$1 ;;
  *) echo "Aufruf: sh deploy/notzugang.sh status|an|aus" >&2; exit 2 ;;
esac
alt=$(grep -c '^WA_EIGENE_ANMELDUNG=' "$ENV" || true)
if [ "$(jetzt)" = "$soll" ] && [ "$alt" = 0 ]; then
  echo "unverändert: Notzugang ist schon $soll."
  [ "$soll" = aus ] || weg
  exit 0
fi
# Zeile ersetzen bzw. anhängen (frühere Zeile WA_EIGENE_ANMELDUNG entfällt); Inhalt über cat zurückschreiben, damit Rechte und
# Besitzer von .env bleiben
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
grep -v -e '^WA_NOTZUGANG=' -e '^WA_EIGENE_ANMELDUNG=' "$ENV" > "$tmp" || true
if [ -s "$tmp" ] && [ -n "$(tail -c1 "$tmp")" ]; then echo >> "$tmp"; fi
echo "WA_NOTZUGANG=$soll" >> "$tmp"
cat "$tmp" > "$ENV"
[ "$alt" = 0 ] || echo "entfernt:  frühere Zeile WA_EIGENE_ANMELDUNG (Notzugang lag bis 04.11.2026 auf der Kundenseite)"
# shellcheck disable=SC2086  # COMPOSE ist bewusst ein Befehl mit Argumenten
$COMPOSE up -d app-mitarbeiter
if [ "$soll" = an ]; then
  echo "Notzugang OFFEN."
  weg
  echo "Danach wieder schließen: sh deploy/notzugang.sh aus"
else
  echo "Notzugang geschlossen: Mitarbeiter nur über https://dashboard-stafl.de/"
fi
