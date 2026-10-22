#!/usr/bin/env bash
# Testumgebung der CI einrichten (ci.yml: Ende-zu-Ende-Tests, Anmeldung über Keycloak; zwischenspeicher.yml).
#
#   bash .github/scripts/testumgebung.sh e2e      # Python-Abhängigkeiten, Chromium mit Systempaketen
#   bash .github/scripts/testumgebung.sh oidc     # zusätzlich Apache, mod_auth_openidc, PHP-Modul, PostgreSQL
#   bash .github/scripts/testumgebung.sh vorrat   # wie oidc, danach alle Pakete in den Paketvorrat sammeln
#
# Paketvorrat (APT_VORRAT, Standard ~/.cache/stafl-apt): vom Workflow „Zwischenspeicher“ gefüllt und per actions/cache
# bereitgestellt. Vor der Installation übernimmt apt_vorrat.py nur Pakete, deren Prüfsumme zur signierten Paketliste
# passt; fehlende oder veraltete lädt apt wie bisher selbst. Ohne Vorrat verhält sich das Skript wie die frühere
# Einrichtung in ci.yml. Der Hash des Skripts gehört zum Schlüssel des Zwischenspeichers (Paketliste geändert → neuer Vorrat).
set -euo pipefail
HIER="$(cd "$(dirname "$0")" && pwd)"
VORRAT="${APT_VORRAT:-$HOME/.cache/stafl-apt}"
OIDC_PAKETE=(apache2 libapache2-mod-auth-openidc libapache2-mod-php8.3 postgresql)
T0=$(date +%s)
zeit() { echo "[$(( $(date +%s) - T0 )) s] $*"; }

pakete_vorbereiten() {
  sudo apt-get update -q
  if [ -d "$VORRAT" ]; then sudo python3 -I "$HIER/apt_vorrat.py" einsetzen "$VORRAT"; else echo "Paketvorrat: keiner vorhanden."; fi
  zeit "Paketlisten und Vorrat"
}

python_und_browser() {
  python -m pip install -q -r tests/requirements.txt
  zeit "Python-Abhängigkeiten"
  python -m playwright install --with-deps chromium
  zeit "Chromium mit Systempaketen"
}

case "${1:-}" in
e2e)
  pakete_vorbereiten
  python_und_browser
  ;;
oidc|vorrat)
  # Vorrat: heruntergeladene Pakete sicher behalten (apt-get tut das ohnehin; gilt dann auch für „apt“)
  [ "$1" = vorrat ] && echo 'APT::Keep-Downloaded-Packages "true";' | sudo tee /etc/apt/apt.conf.d/99-stafl-vorrat >/dev/null
  pakete_vorbereiten
  sudo apt-get install -y -q "${OIDC_PAKETE[@]}"
  zeit "Apache, mod_auth_openidc, PHP-Modul, PostgreSQL"
  python_und_browser
  if [ "$1" = vorrat ]; then
    rm -rf "$VORRAT"
    sudo python3 -I "$HIER/apt_vorrat.py" sammeln "$VORRAT"
    sudo chown -R "$(id -u):$(id -g)" "$VORRAT"
  fi
  ;;
*)
  echo "Aufruf: $0 e2e|oidc|vorrat" >&2; exit 2 ;;
esac
