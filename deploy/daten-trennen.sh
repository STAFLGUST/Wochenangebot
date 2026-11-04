#!/bin/sh
# Daten trennen (ADR-007 Stufe 2): interne Dokumente (Personal, Nutzer, CRM, Controlling, QS, Dateiablage …) aus dem gemeinsamen
# Ordner daten/ in daten-intern/ verschieben, den nur die Mitarbeiterseite (app-mitarbeiter) und der Postausgang einbinden –
# die Kundenseite (app) sieht sie danach nicht mehr. Welche Dokumente die Kundenseite braucht: regeln/datenverantwortung.toml.
# Nur mit Freigabe des Inhabers, im Wartungsfenster (die Anwendung steht kurz). Im Installationsordner als root:
#
#   sh deploy/daten-trennen.sh status            # Zustand und Plan (ändert nichts, Anwendung läuft weiter)
#   sh deploy/daten-trennen.sh trennen           # Sicherung → Stopp → trennen → Start
#   sh deploy/daten-trennen.sh zusammenfuehren   # zurück in einen Ordner – vor einem Rückfall auf ein Release vor der Trennung
#
# Ablauf und Abbruchverhalten: deploy/daten_trennen.py. Nach einem Fehler bleibt die Anwendung absichtlich gestoppt.
set -eu
cd "$(dirname "$0")/.."
DOCKER=${DOCKER:-docker}
AKTION=${1:-status}
APPS="app app-mitarbeiter postausgang"
case "$AKTION" in status|trennen|zusammenfuehren) ;; *) echo "Aufruf: sh deploy/daten-trennen.sh status|trennen|zusammenfuehren"; exit 2 ;; esac
[ -d daten ] || { echo "Abbruch: daten/ nicht gefunden – im Installationsordner ausführen."; exit 1; }
if [ "$AKTION" = status ]; then
  python3 deploy/daten_trennen.py pruefen daten daten-intern
  exit 0
fi
# Nur mit der Ergänzungsdatei der Anmeldung: nur dort binden app-mitarbeiter und postausgang daten-intern ein
if ! sed -n 's/^COMPOSE_FILE=//p' .env 2>/dev/null | grep -qF deploy/anmeldung/docker-compose.anmeldung.yml \
  || ! grep -q 'WA_DATEN_INTERN' deploy/anmeldung/docker-compose.anmeldung.yml 2>/dev/null; then
  echo "Abbruch, nichts geändert: Die Trennung braucht den Betrieb mit getrennten Containern (COMPOSE_FILE mit deploy/anmeldung/docker-compose.anmeldung.yml)."
  exit 1
fi
# Vorprüfung ohne Stopp: ist nichts zu tun, bleibt die Anwendung unangetastet in Betrieb
if [ "$AKTION" = trennen ] && [ -f daten/.daten-getrennt ] && [ -z "$(python3 deploy/daten_trennen.py pruefen daten daten-intern | sed -n 's/^  //p' | head -1)" ]; then
  echo "Daten sind bereits getrennt – nichts zu tun, die Anwendung läuft unverändert weiter."
  exit 0
fi
if [ "$AKTION" = zusammenfuehren ] && [ ! -f daten/.daten-getrennt ]; then
  echo "Daten sind nicht getrennt – nichts zusammenzuführen, die Anwendung läuft unverändert weiter."
  exit 0
fi
sh deploy/sichern.sh --jetzt
# shellcheck disable=SC2086  # APPS sind bewusst mehrere Dienstnamen
$DOCKER compose stop $APPS
if ! python3 deploy/daten_trennen.py "$AKTION" daten daten-intern --offline; then
  echo "Abbruch – die Anwendung bleibt absichtlich gestoppt. Ursache prüfen (Ausgabe oben), nicht blind neu starten." >&2
  echo "Die Sicherung von eben liegt in sicherungen/. Anleitung: docs/plattform/adr-007-kundencontainer.md (Stufe 2)." >&2
  exit 1
fi
# Eigentümer: Anwendung läuft als www-data (33); ohne Verweisen zu folgen (-h), nur der neue Ordner
if [ -d daten-intern ] && [ ! -L daten-intern ]; then
  chown -R -h 33:33 daten-intern
  chmod 700 daten-intern
fi
# shellcheck disable=SC2086
$DOCKER compose start $APPS
if [ "$AKTION" = trennen ]; then
  echo "Daten getrennt. Jetzt prüfen: Kundenseite (Angebot, Kundenanmeldung, Bestellwunsch), Dashboard, Personal/QS-Dokumente."
else
  echo "Daten wieder in einem Ordner. Erst jetzt auf ein Release vor der Trennung zurückgehen."
fi
