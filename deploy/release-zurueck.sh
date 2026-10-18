#!/bin/sh
# Notfall: auf die Version vor dem letzten Release zurückgehen (Daten bleiben unverändert).
#   sh /opt/wochenangebot/deploy/release-zurueck.sh
# Der zurückgenommene Stand wird nicht erneut automatisch eingespielt; ein neuer Release ist dafür nötig.
set -eu
cd "$(dirname "$0")/.."
VORHER=$(python3 -c "import json; t=open('daten/deployment.php').read(); print(json.loads(t[t.index(chr(10))+1:]).get('vorher',''))" 2>/dev/null || true)
printf '%s' "$VORHER" | grep -qE '^[0-9a-f]{40}$' || { echo "Kein vorheriger Stand bekannt."; exit 1; }
JETZT=$(git rev-parse HEAD)
[ "$VORHER" != "$JETZT" ] || { echo "Vorheriger Stand ist bereits aktiv."; exit 0; }
if [ -f daten/.sqlite-active ] && ! git cat-file -e "$VORHER:app/api/storage.php" 2>/dev/null; then
  echo "SQLite aktiv: Zuerst deploy/datenbank-umschalten.sh rollback ausführen."
  exit 1
fi
echo "$JETZT" > .release-abgelehnt
git reset -q --hard "$VORHER"
if git diff --name-only "$JETZT" "$VORHER" | grep -qE '^(Caddyfile|docker-compose\.yml)$'; then docker compose up -d --force-recreate; fi
echo "Zurückgesetzt auf $(git log -1 --format='%h %s')"
