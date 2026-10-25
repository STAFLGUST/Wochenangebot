#!/bin/sh
# Alte Datendateien aufräumen: Nach der Umschaltung auf SQLite liegen die bisherigen Datendateien (daten/*.php mit
# Angeboten, Kunden, Nutzern, Protokoll …) noch im Datenordner. Die Anwendung liest und schreibt sie nicht mehr, die
# Sicherungen enthalten sie nicht, und der Rückweg (datenbank-umschalten.sh rollback) schreibt alle Dateien neu aus der
# Datenbank. Sie zeigen also nur einen veralteten Stand mit personenbezogenen Daten.
#   sh deploy/altdateien.sh zeigen       – auflisten, ändert nichts
#   sh deploy/altdateien.sh archivieren  – Sicherung, Archiv sicherungen/altdateien-<Zeit>.tar.gz (geprüft), dann entfernen
# Läuft nur bei aktivem SQLite mit fehlerfreier Datenbank. Die Anwendung bleibt in Betrieb: sie greift im SQLite-Betrieb
# nur noch auf die Datenbank und die Statusdateien zu (app/api/storage.php), nie auf diese Dateien.
# Bleiben stehen: Datenbank (.sqlite/, .sqlite-active), Postfach-Schlüssel, Statusdateien (sicherung, deployment),
# index.php, geo/ und alle Sperr- und Punktdateien. Anleitung: docs/datenbank.md („Alte Datendateien aufräumen“).
set -eu
cd "$(dirname "$0")/.."
AKTION=${1:-}
case "$AKTION" in zeigen|archivieren) ;; *) echo "Aufruf: sh deploy/altdateien.sh zeigen|archivieren"; exit 1 ;; esac
if [ ! -f daten/.sqlite-active ]; then
  echo "Abbruch, nichts geändert: SQLite ist nicht aktiv – die Dateien sind die laufenden Daten."
  exit 1
fi
if ! python3 deploy/datenbank.py check daten; then
  echo "Abbruch, nichts geändert: die Datenbankprüfung ist fehlgeschlagen."
  exit 1
fi
if [ "$AKTION" = zeigen ]; then
  python3 deploy/datenbank.py altdateien daten
  exit 0
fi
# Erst eine aktuelle Sicherung der Datenbank, dann das Archiv der Altdateien
sh deploy/sichern.sh --jetzt
mkdir -p sicherungen && chmod 700 sicherungen
ARCHIV="sicherungen/altdateien-$(date -u +%Y-%m-%d_%H%M%S).tar.gz"
python3 deploy/datenbank.py altdateien daten --archiv "$ARCHIV"
echo "Archiv: $(pwd)/$ARCHIV (nur für root lesbar, wird nicht automatisch gelöscht)."
echo "Anwendung läuft unverändert weiter. Ansehen: in einen leeren Ordner entpacken, nie zurück nach daten/ kopieren."
