#!/bin/sh
# Holt neue Versionen aus GitHub und spielt sie ein (läuft alle 2 Minuten per systemd-Timer).
# .env und daten/ werden nie verändert (außer der Statusdatei daten/sicherung.php der Datensicherung).
set -eu
cd /opt/wochenangebot
# Übergang: Solange die Sicherung keine eigene Zeitsteuerung hat (deploy/sicherung-einrichten.sh),
# läuft sie hier mit (höchstens 1× pro Tag). Fehler blockieren die Aktualisierung nicht, werden aber vom
# Sicherungsskript selbst als Status gespeichert und gemeldet.
if ! systemctl is-enabled --quiet wochenangebot-sicherung.timer 2>/dev/null; then
  sh deploy/sichern.sh || echo "Hinweis: Datensicherung fehlgeschlagen – Status im Bereich Sicherheit"
fi
# Bereitstellung des aktiven Stands sicherstellen (Versionsnummern, Prüfliste der Dateiprüfung aus dem Commit). Schreibt
# nur, wenn etwas fehlt – z. B. nach dem ersten Release mit deploy/bereitstellen.py, den noch das alte Skript eingespielt
# hat, oder nach einem „git reset“ von Hand. Eine anders veränderte Datei bleibt unangetastet (meldet die Dateiprüfung).
if [ -f deploy/bereitstellen.py ]; then
  python3 deploy/bereitstellen.py || echo "Hinweis: Bereitstellung unvollständig (Versionsnummern/Prüfliste)"
fi
# Release-Modus (nach deploy/release-modus-einrichten.sh): nur noch von Hand freigegebene Releases einspielen
if [ -f /opt/wochenangebot/.release-modus ]; then
  exec sh deploy/freigabe-einspielen.sh
fi
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0
CHANGED=$(git diff --name-only HEAD origin/main)
git reset -q --hard origin/main
if [ -f deploy/bereitstellen.py ]; then python3 deploy/bereitstellen.py || echo "Hinweis: Bereitstellung unvollständig"; fi
if echo "$CHANGED" | grep -qE '^(Caddyfile|docker-compose\.yml)$'; then
  docker compose up -d --force-recreate
fi
echo "Aktualisiert auf $(git log -1 --format='%h %s')"
