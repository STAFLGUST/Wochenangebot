#!/bin/sh
# Adressverzeichnis für die CRM-Karte laden: Kunden erscheinen auf Hausnummer genau statt am Mittelpunkt ihrer
# Postleitzahl. Quelle OpenStreetMap (ODbL, Auszug Deutschland von Geofabrik), umgewandelt auf dem eigenen Server – beim
# Nachschlagen geht keine Anschrift an fremde Dienste. Nur mit Freigabe des Inhabers ausführen.
#
#   cd /opt/wochenangebot && sh deploy/adressen-laden.sh pruefen   # nur anzeigen: Stand und Größe der Quelle, freier Platz
#   cd /opt/wochenangebot && sh deploy/adressen-laden.sh           # laden bzw. aktualisieren (Download ca. 4,5 GB, Umwandeln geschätzt 20–40 Minuten)
#   cd /opt/wochenangebot && sh deploy/adressen-laden.sh entfernen # Verzeichnis entfernen (Karte zeigt wieder PLZ-Mittelpunkte)
#
# Ablauf: Quelle mit Prüfsumme laden → im Container (python:3.12, pyosmium fest über Prüfsumme, deploy/karte/
# requirements.txt) mit deploy/karte/adressen.py umwandeln → prüfen (Format, Anzahl) → neben der alten Datei
# austauschen. Ziel: daten-karte/adressen.sqlite (geschätzt um 1 GB, nicht in den Sicherungen – jederzeit neu ladbar), im
# Anwendungs-Container nur lesend unter /var/www/karte und nie ausgeliefert (Apache gibt dort nur karte.pmtiles frei).
# Die Quelldatei wird danach gelöscht. Kein Neustart nötig.
set -eu
DOCKER=${DOCKER:-docker}
CURL=${CURL:-curl}
WERKZEUG=${ADRESSEN_WERKZEUG:-python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e}
QUELLE=${ADRESSEN_QUELLE:-https://download.geofabrik.de/europe/germany-latest.osm.pbf}
MIN_ADRESSEN=${ADRESSEN_MIN:-1000000}        # weniger = Quelle unvollständig (Deutschland: viele Millionen)
PLATZ_GB=${ADRESSEN_PLATZ_GB:-12}            # Quelle (ca. 4,5 GB) + Arbeitsdatei + neue und alte Zieldatei
MODUS=${1:-laden}
abbruch() { echo "Abbruch: $*" >&2; exit 1; }
case "$MODUS" in laden|pruefen|entfernen) ;; *) echo "Aufruf: sh deploy/adressen-laden.sh [pruefen|laden|entfernen]" >&2; exit 2 ;; esac
[ -f .env ] && [ -f docker-compose.yml ] && [ -f deploy/karte/adressen.py ] || abbruch "Bitte im Installationsordner ausführen: cd /opt/wochenangebot"
ZIEL=daten-karte
aufraeumen() { rm -f "$ZIEL/adressen-quelle.osm.pbf" "$ZIEL/adressen.neu.sqlite" "$ZIEL/adressen.neu.sqlite.arbeit"; }

if [ "$MODUS" = entfernen ]; then
  aufraeumen
  rm -f "$ZIEL/adressen.sqlite" "$ZIEL/adressen-stand.txt"
  echo "entfernt:  Adressverzeichnis (die CRM-Karte zeigt Kunden wieder am Mittelpunkt ihrer Postleitzahl)"
  exit 0
fi

command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
$DOCKER info >/dev/null 2>&1 || abbruch "Docker ist nicht erreichbar (als root ausführen?)."
mkdir -p "$ZIEL"

# Stand der Quelle (Last-Modified) und Größe, ohne sie zu laden
kopf=$($CURL -sSfIL --max-time 60 "$QUELLE") || abbruch "Quelle nicht erreichbar ($QUELLE)."
STAND=$(printf '%s\n' "$kopf" | tr -d '\r' | awk -F': ' 'tolower($1) == "last-modified" { v = $2 } END { print v }')
GROESSE=$(printf '%s\n' "$kopf" | tr -d '\r' | awk -F': ' 'tolower($1) == "content-length" { v = $2 } END { printf "%d", v / 1048576 }')
[ -n "$STAND" ] || STAND=unbekannt
BISHER=$(cat "$ZIEL/adressen-stand.txt" 2>/dev/null || echo keiner)
frei_gb=$(df -Pk "$ZIEL" | awk 'NR == 2 { printf "%d", $4 / 1048576 }')
echo "Quelle: $STAND, ${GROESSE} MB (bisher: $BISHER) · freier Platz: ${frei_gb} GB"

if [ "$MODUS" = pruefen ]; then
  [ "$frei_gb" -ge "$PLATZ_GB" ] && echo "Platz reicht (nötig mindestens ${PLATZ_GB} GB)." || echo "Zu wenig Platz: nötig mindestens ${PLATZ_GB} GB – zuerst: sh deploy/speicher.sh"
  echo "Nur geprüft – nichts geladen. Laden mit: sh deploy/adressen-laden.sh"
  exit 0
fi

[ "$STAND" = unbekannt ] || [ "$STAND" != "$BISHER" ] || [ ! -s "$ZIEL/adressen.sqlite" ] || { echo "unverändert: Adressverzeichnis ist schon auf dem Stand $STAND"; exit 0; }
[ "$frei_gb" -ge "$PLATZ_GB" ] || abbruch "Zu wenig freier Platz (${frei_gb} GB, nötig mindestens ${PLATZ_GB} GB) – zuerst: sh deploy/speicher.sh"
trap aufraeumen EXIT
aufraeumen

# 1. Quelle laden und mit der veröffentlichten Prüfsumme vergleichen
echo "lade:      $QUELLE …"
$CURL -fSL --retry 3 --max-time 7200 -o "$ZIEL/adressen-quelle.osm.pbf" "$QUELLE" || abbruch "Download fehlgeschlagen – das bisherige Verzeichnis bleibt unverändert."
soll=$($CURL -fsSL --max-time 60 "$QUELLE.md5" | awk '{ print $1 }') || abbruch "Prüfsumme der Quelle nicht abrufbar – nichts geändert."
ist=$(md5sum "$ZIEL/adressen-quelle.osm.pbf" | awk '{ print $1 }')
[ -n "$soll" ] && [ "$soll" = "$ist" ] || abbruch "Prüfsumme der Quelle passt nicht – nichts geändert."

# 2. Umwandeln im Container (pyosmium fest über Prüfsumme)
echo "wandle um: Adressen aus OpenStreetMap → daten-karte/adressen.neu.sqlite (dauert eine Weile) …"
$DOCKER run --rm --network bridge -v "$(pwd)/$ZIEL:/daten" -v "$(pwd)/deploy/karte:/werkzeug:ro" -e PIP_DISABLE_PIP_VERSION_CHECK=1 "$WERKZEUG" \
  sh -c 'pip install -q --no-cache-dir --root-user-action=ignore --no-deps --only-binary=:all: --require-hashes -r /werkzeug/requirements.txt && python3 -I /werkzeug/adressen.py /daten/adressen-quelle.osm.pbf /daten/adressen.neu.sqlite' \
  || abbruch "Umwandeln fehlgeschlagen – das bisherige Verzeichnis bleibt unverändert."

# 3. Prüfen: lesbar, bekanntes Format, plausible Anzahl
anzahl=$(python3 -I -c 'import sqlite3, sys
d = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)
i = dict(d.execute("SELECT schluessel, wert FROM info"))
n = d.execute("SELECT count(*) FROM adressen").fetchone()[0]
print(n if i.get("format") == "1" and str(n) == i.get("adressen") else -1)' "$ZIEL/adressen.neu.sqlite" 2>/dev/null) || anzahl=-1
[ "$anzahl" -ge "$MIN_ADRESSEN" ] || abbruch "Neues Verzeichnis unvollständig oder nicht lesbar ($anzahl Adressen) – verworfen."
chmod 644 "$ZIEL/adressen.neu.sqlite"
mv -f "$ZIEL/adressen.neu.sqlite" "$ZIEL/adressen.sqlite"   # im selben Ordner: sofortiger Austausch
printf '%s\n' "$STAND" > "$ZIEL/adressen-stand.txt"
groesse_mb=$(( $(wc -c < "$ZIEL/adressen.sqlite") / 1048576 ))
echo "geladen:   Adressverzeichnis Stand $STAND, $anzahl Adressen, ${groesse_mb} MB – die CRM-Karte zeigt Kunden ab dem nächsten Öffnen auf Hausnummer genau."
