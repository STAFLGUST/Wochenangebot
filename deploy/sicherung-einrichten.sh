#!/bin/sh
# Einmalig auf dem Server (als root): eigene Zeitsteuerung für die Datensicherung einrichten.
#   sh /opt/wochenangebot/deploy/sicherung-einrichten.sh
# Danach läuft die Sicherung täglich um 02:30 Uhr unabhängig von der Aktualisierung; schlägt sie fehl,
# protokolliert systemd das und das Skript meldet den Fehler (Statuskarte, optional Totmannschalter).
# Rückgängig:  systemctl disable --now wochenangebot-sicherung.timer
set -eu
cd "$(dirname "$0")/.."
cat > /etc/systemd/system/wochenangebot-sicherung.service <<'UNIT'
[Unit]
Description=Wochenangebot: tägliche Datensicherung
After=docker.service

[Service]
Type=oneshot
ExecStart=/bin/sh /opt/wochenangebot/deploy/sichern.sh --jetzt
Nice=10
IOSchedulingClass=idle
UNIT
cat > /etc/systemd/system/wochenangebot-sicherung.timer <<'UNIT'
[Unit]
Description=Wochenangebot: Datensicherung täglich 02:30 Uhr

[Timer]
OnCalendar=*-*-* 02:30:00
RandomizedDelaySec=10min
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now wochenangebot-sicherung.timer
echo "Eingerichtet. Nächster Lauf:"
systemctl list-timers wochenangebot-sicherung.timer --no-pager | head -2
