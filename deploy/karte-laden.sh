#!/bin/sh
# Detailkarte (Straßen, Gebäude, Ortsnamen) für CRM-Karte und Auswertung laden – OpenStreetMap-Daten als eine Datei auf
# dem eigenen Server (keine fremden Kartendienste beim Ansehen). Nur mit Freigabe des Inhabers ausführen.
#
#   cd /opt/wochenangebot && sh deploy/karte-laden.sh pruefen   # nur anzeigen: neuester Stand, geschätzte Größe, Platz
#   cd /opt/wochenangebot && sh deploy/karte-laden.sh           # laden bzw. aktualisieren (dauert je nach Leitung 10–40 Minuten)
#   cd /opt/wochenangebot && sh deploy/karte-laden.sh entfernen # Detailkarte entfernen (die Seiten zeigen wieder die Übersichtskarte)
#
# Zweite Karte „herkunft“ für die Herkunftsbetriebe im Container-Import (EUDR): Südamerika und Neuseeland
# (deploy/karte/herkunft.geojson) bis Zoomstufe 14 (Probelauf 18.11.2026: 4,6 GB; Stufe 12: 1,2 GB). Eine andere Stufe:
# KARTE_HERKUNFT_ZOOM=13 sh deploy/karte-laden.sh laden herkunft – das Skript merkt sie sich (daten-karte/herkunft-zoom.txt),
# spätere Aufrufe ohne Angabe bleiben dabei; eine geänderte Stufe lädt auch bei gleichem Kartenstand neu.
# Zuerst immer prüfen: der Probelauf nennt die Größe.
#   sh deploy/karte-laden.sh pruefen herkunft · sh deploy/karte-laden.sh laden herkunft · sh deploy/karte-laden.sh entfernen herkunft
# Ziel: daten-karte/herkunft.pmtiles, ausgeliefert als /karte/herkunft.pmtiles auf dem Host des Container-Imports.
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
MODUS=${1:-laden}
KARTE=${2:-deutschland}
ZIEL=daten-karte
# Gemerkte Zoomstufe einer Karte (nur Ziffern einer echten Datei – der Ordner ist im Lade-Container beschreibbar); leer = keine
zoom_gemerkt() { [ -f "$1" ] && [ ! -L "$1" ] && head -c 2 "$1" | tr -cd '0-9' | grep -Ex '1[0-5]|[5-9]' || true; }
# Stand-Vermerk lesen, ebenso nur aus einer echten Datei; sonst „keiner“ (gelesen wird vor dem Start des Lade-Containers)
vermerk_lesen() { [ -f "$1" ] && [ ! -L "$1" ] && cat "$1" 2>/dev/null || echo keiner; }
# Je Karte: Region, Dateiname, Vermerk des Stands, Zoomstufe, Mindestgröße (kleiner = abgebrochener Download), nötiger Platz
case "$KARTE" in
  deutschland) REGION=deutschland.geojson; DATEI=karte; VERMERK=stand.txt; MAXZOOM=15; ZOOM_VERMERK=; ZOOM_BISHER=15; NAME="Detailkarte"; GEBIET="Deutschland"
    MIN_GROESSE_MB=${KARTE_MIN_MB:-500}; PLATZ_GB=${KARTE_PLATZ_GB:-14} ;;      # neue Datei (ca. 5–6 GB) neben der alten plus Reserve
  herkunft) REGION=herkunft.geojson; DATEI=herkunft; VERMERK=herkunft-stand.txt; NAME="Herkunftskarte"; GEBIET="Südamerika und Neuseeland"
    # Zoomstufe: die Angabe, sonst die der geladenen Karte, sonst 14. Eine Karte ohne Vermerk der Stufe (geladen vor dieser
    # Fassung) gilt als abweichend und wird beim nächsten Laden einmal neu geholt.
    ZOOM_VERMERK=herkunft-zoom.txt; ZOOM_BISHER=$(zoom_gemerkt "$ZIEL/$ZOOM_VERMERK"); MAXZOOM=${KARTE_HERKUNFT_ZOOM:-${ZOOM_BISHER:-14}}
    MIN_GROESSE_MB=${KARTE_MIN_MB:-100}; PLATZ_GB=${KARTE_PLATZ_GB:-30} ;;      # Stufe 14 rund 5 GB neben der alten Datei; Stufe 15 ungeprüft
  *) echo "Aufruf: sh deploy/karte-laden.sh [pruefen|laden|entfernen] [deutschland|herkunft]" >&2; exit 2 ;;
esac
printf '%s' "$MAXZOOM" | grep -Eq '^(1[0-5]|[5-9])$' || { echo "Abbruch: Zoomstufe $MAXZOOM ungültig (5 bis 15)." >&2; exit 1; }
abbruch() { echo "Abbruch: $*" >&2; exit 1; }
# daten-karte ist im Lade-Container beschreibbar: ein dort untergeschobener Verweis darf root nie auf eine andere Datei
# des Servers umlenken (gleiche Regel wie status_schreiben() in deploy/sichern.sh und ablegen() in deploy/postfach-schluessel.sh).
echt() { [ -f "$1" ] && [ ! -L "$1" ] || abbruch "$1 ist kein echtes Ergebnis des Laufs (Verweis oder Sonderdatei) – verworfen."; }
# Vermerk außerhalb des Container-Ordners erzeugen und nur per Umbenennen einsetzen; mv -fT folgt keinem Verweis, auch keinem auf einen Ordner
vermerken() {
  TMP=$(mktemp "$(pwd)/.stand.XXXXXX") || abbruch "Zwischendatei nicht anlegbar."
  printf '%s\n' "$2" > "$TMP" && chmod 644 "$TMP" && mv -fT "$TMP" "$1" || { rm -f "$TMP"; abbruch "Stand nicht vermerkt."; }
}
case "$MODUS" in laden|pruefen|entfernen) ;; *) echo "Aufruf: sh deploy/karte-laden.sh [pruefen|laden|entfernen] [deutschland|herkunft]" >&2; exit 2 ;; esac
[ -f .env ] && [ -f docker-compose.yml ] && [ -f "deploy/karte/$REGION" ] || abbruch "Bitte im Installationsordner ausführen: cd /opt/wochenangebot"

if [ "$MODUS" = entfernen ]; then
  rm -f "$ZIEL/$DATEI.pmtiles" "$ZIEL/$DATEI.neu.pmtiles" "$ZIEL/$VERMERK" ${ZOOM_VERMERK:+"$ZIEL/$ZOOM_VERMERK"}
  echo "entfernt:  $NAME (die Seiten zeigen wieder die Übersichtskarte)"
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
BISHER=$(vermerk_lesen "$ZIEL/$VERMERK")

frei_gb=$(df -Pk "$ZIEL" | awk 'NR == 2 { printf "%d", $4 / 1048576 }')
echo "Kartenstand: ${STAND%.pmtiles} (bisher: ${BISHER%.pmtiles})${ZOOM_VERMERK:+ · Zoomstufe: $MAXZOOM (bisher: ${ZOOM_BISHER:-keine})} · freier Platz: ${frei_gb} GB"

# Gemeinsame Argumente: Ausschnitt der gewählten Karte bis zu ihrer Zoomstufe
lauf() {
  $DOCKER run --rm --network bridge -v "$(pwd)/$ZIEL:/daten" -v "$(pwd)/deploy/karte:/region:ro" "$WERKZEUG" \
    extract "$QUELLE/$STAND" "$@" --region="/region/$REGION" --maxzoom="$MAXZOOM" --download-threads=4
}

if [ "$MODUS" = pruefen ]; then
  lauf /daten/probe.pmtiles --dry-run || abbruch "Probelauf fehlgeschlagen."
  echo "Nur geprüft – nichts geladen. Laden mit: ${KARTE_HERKUNFT_ZOOM:+KARTE_HERKUNFT_ZOOM=$MAXZOOM }sh deploy/karte-laden.sh laden $KARTE"
  exit 0
fi

[ "$STAND" != "$BISHER" ] || [ "$MAXZOOM" != "$ZOOM_BISHER" ] || [ ! -s "$ZIEL/$DATEI.pmtiles" ] || { echo "unverändert: $NAME ist schon auf dem Stand ${STAND%.pmtiles}${ZOOM_VERMERK:+, Zoomstufe $MAXZOOM}"; exit 0; }
[ "$frei_gb" -ge "$PLATZ_GB" ] || abbruch "Zu wenig freier Platz (${frei_gb} GB, nötig mindestens ${PLATZ_GB} GB) – zuerst: sh deploy/speicher.sh"
rm -f "$ZIEL/$DATEI.neu.pmtiles"
echo "lade:      Ausschnitt $GEBIET bis Zoomstufe $MAXZOOM – das dauert eine Weile …"
lauf "/daten/$DATEI.neu.pmtiles" || { rm -f "$ZIEL/$DATEI.neu.pmtiles"; abbruch "Laden fehlgeschlagen – die bisherige Karte bleibt unverändert."; }

# Prüfen: echtes Ergebnis des Laufs, Größe plausibel, Kopf „PMTiles“ Version 3, das Werkzeug kann die Datei lesen
echt "$ZIEL/$DATEI.neu.pmtiles"
groesse_mb=$(( $(wc -c < "$ZIEL/$DATEI.neu.pmtiles") / 1048576 ))
[ "$groesse_mb" -ge "$MIN_GROESSE_MB" ] || { rm -f "$ZIEL/$DATEI.neu.pmtiles"; abbruch "Neue Karte nur ${groesse_mb} MB – unvollständig, verworfen."; }
[ "$(head -c 7 "$ZIEL/$DATEI.neu.pmtiles")" = PMTiles ] || { rm -f "$ZIEL/$DATEI.neu.pmtiles"; abbruch "Neue Karte hat kein PMTiles-Format – verworfen."; }
$DOCKER run --rm -v "$(pwd)/$ZIEL:/daten:ro" "$WERKZEUG" show "/daten/$DATEI.neu.pmtiles" >/dev/null 2>&1 \
  || { rm -f "$ZIEL/$DATEI.neu.pmtiles"; abbruch "Neue Karte nicht lesbar – verworfen."; }
chmod 644 "$ZIEL/$DATEI.neu.pmtiles"
mv -fT "$ZIEL/$DATEI.neu.pmtiles" "$ZIEL/$DATEI.pmtiles"   # im selben Ordner: sofortiger Austausch, -T ersetzt auch einen Verweis
[ -z "$ZOOM_VERMERK" ] || vermerken "$ZIEL/$ZOOM_VERMERK" "$MAXZOOM"   # zuerst die Stufe: bricht es dazwischen ab, lädt der nächste Lauf neu
vermerken "$ZIEL/$VERMERK" "$STAND"
echo "geladen:   $NAME ($GEBIET) Stand ${STAND%.pmtiles}, Zoomstufe $MAXZOOM, ${groesse_mb} MB – die Karten zeigen ab dem nächsten Öffnen Straßen und Orte."
