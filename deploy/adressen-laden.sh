#!/bin/sh
# Adressverzeichnis für die CRM-Karte laden: Kunden erscheinen auf Hausnummer genau statt am Mittelpunkt ihrer
# Postleitzahl. Quelle OpenStreetMap (ODbL, Auszug Deutschland von Geofabrik), umgewandelt auf dem eigenen Server – beim
# Nachschlagen geht keine Anschrift an fremde Dienste. Nur mit Freigabe des Inhabers ausführen.
#
#   cd /opt/wochenangebot && sh deploy/adressen-laden.sh pruefen   # nur anzeigen: Stand und Größe der Quelle, freier Platz
#   cd /opt/wochenangebot && sh deploy/adressen-laden.sh probe     # nur das Umwandeln im Container mit Testdaten prüfen (ohne Download)
#   cd /opt/wochenangebot && sh deploy/adressen-laden.sh           # laden bzw. aktualisieren (Download ca. 4,5 GB, Umwandeln geschätzt 20–40 Minuten)
#   cd /opt/wochenangebot && sh deploy/adressen-laden.sh entfernen # Verzeichnis entfernen (Karte zeigt wieder PLZ-Mittelpunkte)
#
# Ablauf: Probe (Umwandeln der Testdaten tests/fixtures/karte/adressen.osm im Container – scheitert das Werkzeug, bevor
# 4,5 GB geladen werden) → Quelle laden und prüfen (veröffentlichte MD5-Prüfsumme, sonst Größe) → im Container
# (python:3.12, pyosmium fest über Prüfsumme, deploy/karte/requirements.txt) mit deploy/karte/adressen.py umwandeln →
# prüfen (Format, Anzahl) → neben der alten Datei austauschen. Ziel: daten-karte/adressen.sqlite (geschätzt um 1 GB, nicht
# in den Sicherungen – jederzeit neu ladbar), im Anwendungs-Container nur lesend unter /var/www/karte und nie ausgeliefert
# (Apache gibt dort nur karte.pmtiles frei). Die Quelldatei wird danach gelöscht. Kein Neustart nötig.
# Volles Python-Image (nicht „slim“): das pyosmium-Paket braucht libexpat aus dem System, die im slim-Image fehlt.
set -eu
DOCKER=${DOCKER:-docker}
CURL=${CURL:-curl}
WERKZEUG=${ADRESSEN_WERKZEUG:-python:3.12.14-bookworm@sha256:dbbe4ceb97851e2e5fa83798b239811f871cb743b259ba3563737349f6bcfaa0}
QUELLE=${ADRESSEN_QUELLE:-https://download.geofabrik.de/europe/germany-latest.osm.pbf}
MIN_ADRESSEN=${ADRESSEN_MIN:-1000000}        # weniger = Quelle unvollständig (Deutschland: viele Millionen)
PLATZ_GB=${ADRESSEN_PLATZ_GB:-12}            # Quelle (ca. 4,5 GB) + Arbeitsdatei + neue und alte Zieldatei
MODUS=${1:-laden}
abbruch() { echo "Abbruch: $*" >&2; exit 1; }
case "$MODUS" in laden|pruefen|probe|entfernen) ;; *) echo "Aufruf: sh deploy/adressen-laden.sh [pruefen|probe|laden|entfernen]" >&2; exit 2 ;; esac
[ -f .env ] && [ -f docker-compose.yml ] && [ -f deploy/karte/adressen.py ] || abbruch "Bitte im Installationsordner ausführen: cd /opt/wochenangebot"
ZIEL=daten-karte
aufraeumen() { rm -f "$ZIEL/adressen-quelle.osm.pbf" "$ZIEL/adressen.neu.sqlite" "$ZIEL/adressen.neu.sqlite.arbeit" "$ZIEL/adressen-probe.sqlite" "$ZIEL/adressen-probe.sqlite.arbeit"; }

if [ "$MODUS" = entfernen ]; then
  aufraeumen
  rm -f "$ZIEL/adressen.sqlite" "$ZIEL/adressen-stand.txt"
  echo "entfernt:  Adressverzeichnis (die CRM-Karte zeigt Kunden wieder am Mittelpunkt ihrer Postleitzahl)"
  exit 0
fi

command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
$DOCKER info >/dev/null 2>&1 || abbruch "Docker ist nicht erreichbar (als root ausführen?)."
mkdir -p "$ZIEL"

# Umwandeln im Container: umwandeln <Quelle im Container> <Ziel im Container> – pyosmium fest über Prüfsummen, ohne
# Abhängigkeiten; /daten = daten-karte, /probe = Testdaten (nur lesend)
umwandeln() {
  $DOCKER run --rm --network bridge -v "$(pwd)/$ZIEL:/daten" -v "$(pwd)/deploy/karte:/werkzeug:ro" -v "$(pwd)/tests/fixtures/karte:/probe:ro" \
    -e PIP_DISABLE_PIP_VERSION_CHECK=1 "$WERKZEUG" \
    sh -c 'pip install -q --no-cache-dir --root-user-action=ignore --no-deps --only-binary=:all: --require-hashes -r /werkzeug/requirements.txt && python3 -I /werkzeug/adressen.py "$1" "$2"' sh "$1" "$2"
}
# Anzahl der Adressen einer erzeugten Datei (bekanntes Format, Zählung stimmt mit dem Vermerk überein), sonst -1
anzahl_in() {
  python3 -I -c 'import sqlite3, sys
d = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)
i = dict(d.execute("SELECT schluessel, wert FROM info"))
n = d.execute("SELECT count(*) FROM adressen").fetchone()[0]
print(n if i.get("format") == "1" and str(n) == i.get("adressen") else -1)' "$1" 2>/dev/null || echo -1
}
# Probe: Testdaten im Container umwandeln – prüft Image, pyosmium und Umwandlung, ohne die Quelle zu laden
probe() {
  [ -f tests/fixtures/karte/adressen.osm ] || abbruch "Testdaten für die Probe fehlen (tests/fixtures/karte/adressen.osm)."
  rm -f "$ZIEL/adressen-probe.sqlite"
  umwandeln /probe/adressen.osm /daten/adressen-probe.sqlite || { rm -f "$ZIEL/adressen-probe.sqlite"; abbruch "Probe fehlgeschlagen: Umwandeln im Container funktioniert nicht – nichts geladen, nichts geändert."; }
  n=$(anzahl_in "$ZIEL/adressen-probe.sqlite"); rm -f "$ZIEL/adressen-probe.sqlite"
  [ "$n" -ge 1 ] || abbruch "Probe fehlgeschlagen: keine Testadressen umgewandelt – nichts geladen, nichts geändert."
  echo "Probe:     Umwandeln im Container funktioniert ($n Testadressen)"
}
if [ "$MODUS" = probe ]; then
  probe
  exit 0
fi

# Stand der Quelle (Last-Modified), Größe in Bytes und tatsächliche Adresse (nach Weiterleitungen), ohne sie zu laden
kopf=$($CURL -sSfIL --max-time 60 -w '\nurl_effective: %{url_effective}\n' "$QUELLE") || abbruch "Quelle nicht erreichbar ($QUELLE)."
kopfwert() { printf '%s\n' "$kopf" | tr -d '\r' | awk -F': ' -v k="$1" 'tolower($1) == k { v = $2 } END { print v }'; }
STAND=$(kopfwert last-modified)
BYTES=$(kopfwert content-length | tr -cd '0-9'); BYTES=${BYTES:-0}
ADRESSE=$(kopfwert url_effective); ADRESSE=${ADRESSE:-$QUELLE}
GROESSE=$((BYTES / 1048576))
[ -n "$STAND" ] || STAND=unbekannt
# Veröffentlichte MD5-Prüfsumme: neben der Datei bzw. neben dem Ziel einer Weiterleitung; leer, wenn keine abrufbar ist
pruefsumme() {
  for u in "$QUELLE.md5" "$ADRESSE.md5"; do
    s=$($CURL -fsSL --max-time 60 "$u" 2>/dev/null | awk 'NR == 1 { print tolower($1) }')
    if printf '%s' "$s" | grep -Eq '^[0-9a-f]{32}$'; then echo "$s"; return 0; fi
  done
}
BISHER=$(cat "$ZIEL/adressen-stand.txt" 2>/dev/null || echo keiner)
frei_gb=$(df -Pk "$ZIEL" | awk 'NR == 2 { printf "%d", $4 / 1048576 }')
echo "Quelle: $STAND, ${GROESSE} MB (bisher: $BISHER) · freier Platz: ${frei_gb} GB"

if [ "$MODUS" = pruefen ]; then
  [ "$frei_gb" -ge "$PLATZ_GB" ] && echo "Platz reicht (nötig mindestens ${PLATZ_GB} GB)." || echo "Zu wenig Platz: nötig mindestens ${PLATZ_GB} GB – zuerst: sh deploy/speicher.sh"
  [ -n "$(pruefsumme)" ] && echo "Prüfsumme (MD5) der Quelle abrufbar." || echo "Keine Prüfsumme der Quelle abrufbar – beim Laden wird die Größe geprüft."
  echo "Nur geprüft – nichts geladen. Laden mit: sh deploy/adressen-laden.sh"
  exit 0
fi

[ "$STAND" = unbekannt ] || [ "$STAND" != "$BISHER" ] || [ ! -s "$ZIEL/adressen.sqlite" ] || { echo "unverändert: Adressverzeichnis ist schon auf dem Stand $STAND"; exit 0; }
[ "$frei_gb" -ge "$PLATZ_GB" ] || abbruch "Zu wenig freier Platz (${frei_gb} GB, nötig mindestens ${PLATZ_GB} GB) – zuerst: sh deploy/speicher.sh"
trap aufraeumen EXIT
aufraeumen
probe

# 1. Quelle laden und prüfen: mit der veröffentlichten Prüfsumme, sonst über die angekündigte Größe (das Umwandeln liest
#    danach jeden Block der Datei; beschädigte Daten brechen dort ab)
echo "lade:      $QUELLE …"
$CURL -fSL --retry 3 --max-time 7200 -o "$ZIEL/adressen-quelle.osm.pbf" "$QUELLE" || abbruch "Download fehlgeschlagen – das bisherige Verzeichnis bleibt unverändert."
soll=$(pruefsumme)
if [ -n "$soll" ]; then
  ist=$(md5sum "$ZIEL/adressen-quelle.osm.pbf" | awk '{ print $1 }')
  [ "$soll" = "$ist" ] || abbruch "Prüfsumme der Quelle passt nicht (Download beschädigt oder Quelle inzwischen erneuert) – nichts geändert, bitte noch einmal starten."
  echo "geprüft:   Prüfsumme (MD5) stimmt"
else
  ist_bytes=$(wc -c < "$ZIEL/adressen-quelle.osm.pbf" | tr -cd '0-9')
  [ "$BYTES" -gt 0 ] && [ "$ist_bytes" = "$BYTES" ] || abbruch "Download unvollständig ($ist_bytes von $BYTES Bytes) – nichts geändert, bitte noch einmal starten."
  echo "geprüft:   Größe stimmt ($ist_bytes Bytes; keine Prüfsumme der Quelle abrufbar)"
fi

# 2. Umwandeln im Container
echo "wandle um: Adressen aus OpenStreetMap → daten-karte/adressen.neu.sqlite (dauert eine Weile) …"
umwandeln /daten/adressen-quelle.osm.pbf /daten/adressen.neu.sqlite || abbruch "Umwandeln fehlgeschlagen – das bisherige Verzeichnis bleibt unverändert."

# 3. Prüfen: lesbar, bekanntes Format, plausible Anzahl
anzahl=$(anzahl_in "$ZIEL/adressen.neu.sqlite")
[ "$anzahl" -ge "$MIN_ADRESSEN" ] || abbruch "Neues Verzeichnis unvollständig oder nicht lesbar ($anzahl Adressen) – verworfen."
chmod 644 "$ZIEL/adressen.neu.sqlite"
mv -f "$ZIEL/adressen.neu.sqlite" "$ZIEL/adressen.sqlite"   # im selben Ordner: sofortiger Austausch
printf '%s\n' "$STAND" > "$ZIEL/adressen-stand.txt"
groesse_mb=$(( $(wc -c < "$ZIEL/adressen.sqlite") / 1048576 ))
echo "geladen:   Adressverzeichnis Stand $STAND, $anzahl Adressen, ${groesse_mb} MB – die CRM-Karte zeigt Kunden ab dem nächsten Öffnen auf Hausnummer genau."
