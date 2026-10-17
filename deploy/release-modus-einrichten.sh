#!/bin/sh
# Einmalig auf dem Server (als root): Release-Modus einschalten.
#   sh /opt/wochenangebot/deploy/release-modus-einrichten.sh
# Danach spielt die Aktualisierung nur noch Commits ein, die in GitHub über den Workflow „Release“ von Hand
# freigegeben wurden und deren CI erfolgreich war. Ein Merge nach main allein ändert die Live-Seite nicht mehr.
# Zurück zum bisherigen Verhalten:  rm /opt/wochenangebot/.release-modus
set -eu
cd "$(dirname "$0")/.."
envwert() { sed -n "s/^$1=//p" .env 2>/dev/null | head -1 | tr -d '"'"'"' '; }
[ -n "$(envwert GITHUB_REPO)" ] || { echo "Bitte zuerst in .env eintragen: GITHUB_REPO=STAFLGUST/Wochenangebot"; exit 1; }
[ -n "$(envwert GITHUB_TOKEN_LESEN)" ] || { echo "Bitte zuerst in .env eintragen: GITHUB_TOKEN_LESEN=… (nur Lesen, nur dieses Repository)"; exit 1; }
command -v python3 >/dev/null || { echo "python3 fehlt (apt install python3)"; exit 1; }
chmod 600 .env
# Token testen, ohne ihn auszugeben
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(envwert GITHUB_TOKEN_LESEN)" \
  "https://api.github.com/repos/$(envwert GITHUB_REPO)/actions/workflows/release.yml/runs?per_page=1")
[ "$code" = 200 ] || { echo "Token oder Repository ungültig (GitHub antwortet $code). Ist release.yml schon auf main?"; exit 1; }
git rev-parse HEAD > .release-letzter-stand
touch .release-modus
echo "Release-Modus eingeschaltet. Aktueller Stand: $(git log -1 --format='%h %s')"
echo "Neue Versionen gehen erst live, wenn Sie in GitHub unter Actions → Release → Run workflow freigeben."
