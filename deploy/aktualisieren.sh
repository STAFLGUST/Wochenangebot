#!/bin/sh
# Holt neue Versionen aus GitHub und spielt sie ein (läuft alle 2 Minuten per systemd-Timer).
# .env und daten/ werden nie verändert.
set -eu
cd /opt/wochenangebot
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0
CHANGED=$(git diff --name-only HEAD origin/main)
git reset -q --hard origin/main
if echo "$CHANGED" | grep -qE '^(Caddyfile|docker-compose\.yml)$'; then
  docker compose up -d --force-recreate
fi
echo "Aktualisiert auf $(git log -1 --format='%h %s')"
