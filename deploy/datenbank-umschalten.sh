#!/bin/sh
# Speicher umschalten: Dateien → SQLite (migrate) oder zurück (rollback), im Wartungsfenster durch den Betreiber.
# Nur nach dem vom Inhaber freigegebenen Release mit Datenbankunterstützung. Wird nie automatisch aufgerufen.
# Ablauf: Vorprüfung (ohne Stopp) → Sicherung → PDO_SQLITE im Container prüfen → App stoppen → übernehmen und
# vergleichen (deploy/datenbank.py) → Eigentümer setzen → App starten. Anleitung: docs/datenbank.md
set -eu
cd "$(dirname "$0")/.."
DOCKER=${DOCKER:-docker}
AKTION=${1:-}
case "$AKTION" in migrate|rollback) ;; *) echo "Aufruf: sh deploy/datenbank-umschalten.sh migrate|rollback"; exit 1 ;; esac
# Vorprüfung vor Sicherung und Stopp: ist nichts umzuschalten, bleibt die Anwendung unangetastet in Betrieb.
if [ "$AKTION" = migrate ]; then
  if [ -f daten/.sqlite-active ]; then
    echo "SQLite ist bereits aktiv – nichts zu tun, die Anwendung läuft unverändert weiter."
    echo "Prüfen: python3 deploy/datenbank.py check daten"
    exit 0
  fi
  if [ -e daten/.sqlite ]; then
    echo "Abbruch, nichts geändert: daten/.sqlite ist vorhanden, SQLite aber nicht aktiv (Rest einer früheren Migration oder eines Rückfalls)."
    echo "Ordner bei gestoppter Anwendung archivieren oder umbenennen (docs/datenbank.md, Abschnitt Rückfall), dann erneut aufrufen."
    exit 1
  fi
elif [ ! -f daten/.sqlite-active ]; then
  echo "SQLite ist nicht aktiv – nichts zurückzuschalten, die Anwendung läuft unverändert weiter."
  exit 0
fi
# Existing backup process must succeed before stopping the app.
sh deploy/sichern.sh --jetzt
# Confirm the actual runtime before activating a database.
$DOCKER compose exec -T app php -r 'exit(in_array("sqlite", PDO::getAvailableDrivers(), true) ? 0 : 1);'
$DOCKER compose stop app
# On any failure leave the app stopped: operator can inspect; do not serve partially exported files.
if ! python3 deploy/datenbank.py "$AKTION" daten --offline; then
  echo "Umschalten fehlgeschlagen – die Anwendung bleibt absichtlich gestoppt. Ursache prüfen (Ausgabe oben), nicht blind neu starten." >&2
  echo "Die Sicherung von eben liegt in sicherungen/. Anleitung: docs/datenbank.md" >&2
  exit 1
fi
# Eigentümer setzen, ohne Verweisen zu folgen: daten/ ist im Container beschreibbar (-h und -type f: nie das Ziel
# eines dort angelegten Verweises; chmod nur auf echte Ordner/Dateien, die datenbank.py eben angelegt hat)
chown -h 33:33 daten/.storage.lock
if [ "$AKTION" = migrate ]; then
  [ -d daten/.sqlite ] && [ ! -L daten/.sqlite ] && [ -f daten/.sqlite/store.sqlite ] && [ ! -L daten/.sqlite/store.sqlite ] \
    || { echo "Unerwarteter Eintrag in daten/.sqlite – Anwendung bleibt gestoppt, bitte prüfen." >&2; exit 1; }
  chown -R -h 33:33 daten/.sqlite
  chmod 700 daten/.sqlite
  chmod 600 daten/.sqlite/store.sqlite
else
  find daten -type f -name '*.php' -exec chown -h 33:33 {} +
fi
$DOCKER compose start app
echo "Speicher umgeschaltet. Anmeldung, Kundenangebot, Entwurf und Bestellwunsch jetzt prüfen."
