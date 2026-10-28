#!/bin/sh
# Speicherbelegung des Servers anzeigen und gefahrlos Aufräumbares entfernen (Docker-Zwischenspeicher, ungenutzte Images).
#
#   cd /opt/wochenangebot && sh deploy/speicher.sh              # nur anzeigen – ändert nichts
#   cd /opt/wochenangebot && sh deploy/speicher.sh aufraeumen   # Docker-Bauzwischenspeicher und ungenutzte Images entfernen
#
# Nie angefasst: daten/, sicherungen/, daten-anmeldung/, daten-karte/ (Detailkarte, deploy/karte-laden.sh), Docker-Volumes (Keycloak-Datenbank, HTTPS-Zertifikate),
# Container (auch angehaltene) und alle Images, die ein Container nutzt. Images „stafl-app:*“ bleiben immer erhalten –
# darunter das gemerkte Image für den Rückfall (stafl-app:release-vorher, deploy/release-zurueck.sh).
# Container-Protokolle sind seit der Begrenzung in den Compose-Dateien (3 × 10 MB je Dienst) klein; alte, große
# Protokolle verschwinden, sobald ein Release die Container neu erstellt.
set -eu
DOCKER=${DOCKER:-docker}
MODUS=${1:-pruefen}
case "$MODUS" in pruefen|aufraeumen) ;; *) echo "Aufruf: sh deploy/speicher.sh [pruefen|aufraeumen]" >&2; exit 2 ;; esac
[ -f .env ] && [ -f docker-compose.yml ] || { echo "Bitte im Installationsordner ausführen: cd /opt/wochenangebot" >&2; exit 1; }

DOCKER_OK=1; $DOCKER info >/dev/null 2>&1 || DOCKER_OK=0
if [ "$DOCKER_OK" = 0 ]; then
  [ "$MODUS" = aufraeumen ] && { echo "Docker ist nicht erreichbar (als root ausführen?) – nichts aufgeräumt." >&2; exit 1; }
  echo "Hinweis: Docker ist nicht erreichbar (als root ausführen?) – Angaben zu Docker fehlen."; echo
fi
groesse() { du -sh "$1" 2>/dev/null | cut -f1; }
anzahl() { find "$1" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l | tr -d ' '; }

# Images, die bleiben müssen: von einem Container genutzt (Kennung) oder stafl-app:* (Release und Rückfall)
behalten() {
  for c in $($DOCKER ps -aq --no-trunc); do $DOCKER inspect -f '{{.Image}}' "$c"; done
  $DOCKER images --no-trunc --format '{{.ID}} {{.Repository}}' | awk '$2 == "stafl-app" { print $1 }'
}
ungenutzt() {
  b=$(behalten | sort -u)
  $DOCKER images --no-trunc --format '{{.ID}} {{.Repository}}:{{.Tag}} {{.Size}}' | sort -u | while read -r id name size; do
    printf '%s\n' "$b" | grep -qx "$id" || printf '%s %s %s\n' "$id" "$name" "$size"
  done
}

echo "== Plattenplatz"
df -h . | tail -1
echo
if [ "$DOCKER_OK" = 1 ]; then
echo "== Docker (Images, Container, Volumes, Bauzwischenspeicher)"
$DOCKER system df || true
echo
echo "== Container-Protokolle"
for c in $($DOCKER ps -aq); do
  pfad=$($DOCKER inspect -f '{{.LogPath}}' "$c" 2>/dev/null || true)
  name=$($DOCKER inspect -f '{{.Name}}' "$c" 2>/dev/null | sed 's#^/##' || true)
  printf '%8s  %s\n' "$( [ -n "$pfad" ] && groesse "$pfad" || echo '?')" "$name"
done
echo
fi
echo "== Daten und Sicherungen"
printf '%8s  %s\n' "$(groesse daten)" "daten/ (Geschäftsdaten)"
[ -d daten/.sqlite ] && printf '%8s  %s\n' "$(groesse daten/.sqlite)" "daten/.sqlite (Speicher SQLite)"
[ -d daten/protokoll ] && printf '%8s  %s\n' "$(groesse daten/protokoll)" "daten/protokoll ($(anzahl daten/protokoll) Monate Aktivitätsprotokoll)"
[ -d daten/versionen ] && printf '%8s  %s\n' "$(groesse daten/versionen)" "daten/versionen ($(anzahl daten/versionen) frühere Veröffentlichungen, begrenzt)"
[ -d daten/historie ] && printf '%8s  %s\n' "$(groesse daten/historie)" "daten/historie ($(anzahl daten/historie) Wochen Preisverlauf)"
[ -d sicherungen ] && printf '%8s  %s\n' "$(groesse sicherungen)" "sicherungen/ ($(anzahl sicherungen) Dateien, je Art die letzten 30)"
[ -d daten-anmeldung ] && printf '%8s  %s\n' "$(groesse daten-anmeldung)" "daten-anmeldung/ (Keycloak-Einrichtung)"
[ -d ../wochenangebot-test ] && printf '%8s  %s\n' "$(groesse ../wochenangebot-test)" "/opt/wochenangebot-test (Testumgebung)"
echo
echo "== Aufräumbar ohne Risiko"
U=""; [ "$DOCKER_OK" = 1 ] && U=$(ungenutzt)
if [ -n "$U" ]; then echo "Ungenutzte Images (kein Container nutzt sie, nicht stafl-app):"; printf '%s\n' "$U" | awk '{ printf "  %s  %s\n", $3, $2 }'
else echo "Keine ungenutzten Images."; fi
echo "Bauzwischenspeicher: siehe Zeile Build Cache oben (Spalte RECLAIMABLE)."

[ "$MODUS" = aufraeumen ] || { echo; echo "Nichts verändert. Aufräumen: sh deploy/speicher.sh aufraeumen"; exit 0; }

echo
echo "== Aufräumen"
$DOCKER builder prune -f || echo "Hinweis: Bauzwischenspeicher ließ sich nicht leeren."
printf '%s\n' "$U" | while read -r id name _; do
  [ -n "$id" ] || continue
  ziel=$name; case "$name" in *'<none>'*) ziel=$id ;; esac   # mit Namen nur dieses Etikett, ohne Namen über die Kennung
  # ohne -f: ein Image, das doch genutzt wird, lehnt Docker ab
  if $DOCKER image rm "$ziel" >/dev/null 2>&1; then echo "entfernt: $name"; else echo "bleibt (abgelehnt, z. B. in Benutzung): $name"; fi
done
$DOCKER image prune -f >/dev/null || true
echo
df -h . | tail -1
echo "Fertig. Daten, Sicherungen, Volumes und Container sind unverändert."
