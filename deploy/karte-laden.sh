#!/bin/sh
# Detailkarte (Straßen, Gebäude, Ortsnamen) für CRM-Karte und Auswertung laden – OpenStreetMap-Daten als eine Datei auf
# dem eigenen Server (keine fremden Kartendienste beim Ansehen). Nur mit Freigabe des Inhabers ausführen.
#
#   cd /opt/wochenangebot && sh deploy/karte-laden.sh pruefen   # nur anzeigen: neuester Stand, geschätzte Größe, Platz
#   cd /opt/wochenangebot && sh deploy/karte-laden.sh           # laden bzw. aktualisieren (dauert je nach Leitung 10–40 Minuten)
#   cd /opt/wochenangebot && sh deploy/karte-laden.sh entfernen # Detailkarte entfernen (die Seiten zeigen wieder die Übersichtskarte)
#
# Quelle: täglicher Gesamtstand von Protomaps (OpenStreetMap, ODbL), Ausschnitt Deutschland mit ca. 20 km Rand
# (deploy/karte/deutschland.geojson) bis Zoomstufe 15 (Gebäude und alle Straßen). Werkzeug: go-pmtiles (Protomaps,
# BSD-3) als Container mit fester Version und Prüfsumme. Ziel: daten-karte/karte.pmtiles (nicht in den Sicherungen –
# jederzeit neu ladbar), im Anwendungs-Container nur lesend unter /var/www/karte, ausgeliefert nur auf den Hosts der
# Verwaltung und des CRM und nur mit Anmeldung (deploy/anmeldung/apache-oidc.conf).
# Die neue Datei entsteht neben der alten und ersetzt sie erst nach erfolgreicher Prüfung – kein Neustart nötig.
set -eu
DOCKER=${DOCKER:-docker}
CURL=${CURL:-curl}
WERKZEUG=${KARTE_WERKZEUG:-protomaps/go-pmtiles:v1.31.2@sha256:06574f01f55a78f78f887bc7ebf729a5c093c0d6e17d9876300cfcb0758b59d3}
QUELLE=${KARTE_QUELLE:-https://build.protomaps.com}
METADATEN=${KARTE_METADATEN:-https://build-metadata.protomaps.dev/builds.json}
MAXZOOM=15
MIN_GROESSE_MB=${KARTE_MIN_MB:-500}          # kleiner = abgebrochener Download
PLATZ_GB=${KARTE_PLATZ_GB:-14}               # neue Datei (ca. 5–6 GB) neben der alten plus Reserve
MODUS=${1:-laden}
abbruch() { echo "Abbruch: $*" >&2; exit 1; }
case "$MODUS" in laden|pruefen|entfernen) ;; *) echo "Aufruf: sh deploy/karte-laden.sh [pruefen|laden|entfernen]" >&2; exit 2 ;; esac
[ -f .env ] && [ -f docker-compose.yml ] && [ -f deploy/karte/deutschland.geojson ] || abbruch "Bitte im Installationsordner ausführen: cd /opt/wochenangebot"
ZIEL=daten-karte

if [ "$MODUS" = entfernen ]; then
  rm -f "$ZIEL/karte.pmtiles" "$ZIEL/karte.neu.pmtiles" "$ZIEL/stand.txt"
  echo "entfernt:  Detailkarte (CRM-Karte und Auswertung zeigen wieder die Übersichtskarte)"
  exit 0
fi

command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
$DOCKER info >/dev/null 2>&1 || abbruch "Docker ist nicht erreichbar (als root ausführen?)."
mkdir -p "$ZIEL"

# Neuester vollständiger Tagesstand (Liste der Builds von Protomaps; Name JJJJMMTT.pmtiles)
STAND=${KARTE_STAND:-}
if [ -z "$STAND" ]; then
  liste=$($CURL -sSf --max-time 60 "$METADATEN") || abbruch "Liste der Kartenstände nicht abrufbar ($METADATEN)."
  STAND=$(printf '%s' "$liste" | python3 -c 'import json,re,sys; k=[b["key"] for b in json.load(sys.stdin) if re.fullmatch(r"\d{8}\.pmtiles", str(b.get("key","")))]; print(sorted(k)[-1] if k else "")')
fi
printf '%s' "$STAND" | grep -Eq '^[0-9]{8}\.pmtiles$' || abbruch "Kein gültiger Kartenstand gefunden ('$STAND')."
BISHER=$(cat "$ZIEL/stand.txt" 2>/dev/null || echo keiner)

frei_gb=$(df -Pk "$ZIEL" | awk 'NR == 2 { printf "%d", $4 / 1048576 }')
echo "Kartenstand: ${STAND%.pmtiles} (bisher: ${BISHER%.pmtiles}) · freier Platz: ${frei_gb} GB"

# Gemeinsame Argumente: Ausschnitt Deutschland, bis Zoomstufe 15
lauf() {
  $DOCKER run --rm --network bridge -v "$(pwd)/$ZIEL:/daten" -v "$(pwd)/deploy/karte:/region:ro" "$WERKZEUG" \
    extract "$QUELLE/$STAND" "$@" --region=/region/deutschland.geojson --maxzoom=$MAXZOOM --download-threads=4
}

if [ "$MODUS" = pruefen ]; then
  lauf /daten/probe.pmtiles --dry-run || abbruch "Probelauf fehlgeschlagen."
  echo "Nur geprüft – nichts geladen. Laden mit: sh deploy/karte-laden.sh"
  exit 0
fi

[ "$STAND" != "$BISHER" ] || [ ! -s "$ZIEL/karte.pmtiles" ] || { echo "unverändert: Detailkarte ist schon auf dem Stand ${STAND%.pmtiles}"; exit 0; }
[ "$frei_gb" -ge "$PLATZ_GB" ] || abbruch "Zu wenig freier Platz (${frei_gb} GB, nötig mindestens ${PLATZ_GB} GB) – zuerst: sh deploy/speicher.sh"
rm -f "$ZIEL/karte.neu.pmtiles"
echo "lade:      Ausschnitt Deutschland bis Zoomstufe $MAXZOOM – das dauert eine Weile …"
lauf /daten/karte.neu.pmtiles || { rm -f "$ZIEL/karte.neu.pmtiles"; abbruch "Laden fehlgeschlagen – die bisherige Karte bleibt unverändert."; }

# Prüfen: Größe plausibel, Kopf „PMTiles“ Version 3, das Werkzeug kann die Datei lesen
groesse_mb=$(( $(wc -c < "$ZIEL/karte.neu.pmtiles") / 1048576 ))
[ "$groesse_mb" -ge "$MIN_GROESSE_MB" ] || { rm -f "$ZIEL/karte.neu.pmtiles"; abbruch "Neue Karte nur ${groesse_mb} MB – unvollständig, verworfen."; }
[ "$(head -c 7 "$ZIEL/karte.neu.pmtiles")" = PMTiles ] || { rm -f "$ZIEL/karte.neu.pmtiles"; abbruch "Neue Karte hat kein PMTiles-Format – verworfen."; }
$DOCKER run --rm -v "$(pwd)/$ZIEL:/daten:ro" "$WERKZEUG" show /daten/karte.neu.pmtiles >/dev/null 2>&1 \
  || { rm -f "$ZIEL/karte.neu.pmtiles"; abbruch "Neue Karte nicht lesbar – verworfen."; }
chmod 644 "$ZIEL/karte.neu.pmtiles"
mv -f "$ZIEL/karte.neu.pmtiles" "$ZIEL/karte.pmtiles"   # im selben Ordner: sofortiger Austausch
printf '%s\n' "$STAND" > "$ZIEL/stand.txt"
echo "geladen:   Detailkarte Stand ${STAND%.pmtiles}, ${groesse_mb} MB – CRM-Karte und Auswertung zeigen ab dem nächsten Öffnen Straßen und Gebäude."
