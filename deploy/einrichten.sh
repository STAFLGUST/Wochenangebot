#!/bin/sh
# Einmalig auf dem Server ausführen: richtet die automatische Aktualisierung ein.
set -eu
cd /opt/wochenangebot
chmod +x deploy/aktualisieren.sh
rm -f LIESMICH.txt   # alte Anleitung aus dem ZIP-Paket (jetzt LIESMICH.md)
cat > /etc/systemd/system/wochenangebot-update.service <<'UNIT'
[Unit]
Description=Wochenangebot aus GitHub aktualisieren
After=network-online.target docker.service

[Service]
Type=oneshot
ExecStart=/opt/wochenangebot/deploy/aktualisieren.sh
UNIT
cat > /etc/systemd/system/wochenangebot-update.timer <<'UNIT'
[Unit]
Description=Wochenangebot alle 2 Minuten aktualisieren

[Timer]
OnBootSec=1min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now wochenangebot-update.timer
chown -R 33:33 daten
docker compose up -d --force-recreate
echo
echo "Fertig. Automatische Aktualisierung aktiv:"
systemctl list-timers wochenangebot-update.timer --no-pager | head -2
