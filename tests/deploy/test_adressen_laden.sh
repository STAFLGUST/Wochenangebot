#!/bin/sh
# Test von deploy/adressen-laden.sh – mit Platzhaltern für docker und curl, in einem Wegwerf-Ordner (lädt nichts herunter).
# Der docker-Platzhalter baut das Verzeichnis aus den Testadressen (deploy/karte/adressen.py --json), wie es der Container
# aus OpenStreetMap-Daten täte.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
printf 'PBF-TESTDATEN' > "$T/quelle"
echo 'Mon, 26 Oct 2026 20:21:00 GMT' > "$T/stand"
cat > "$T/curl" <<STUB
#!/bin/sh
echo "\$*" >> "$T/aufrufe"
[ -f "$T/ohne-netz" ] && exit 6
ziel=""; url=""; kopf=0
while [ \$# -gt 0 ]; do
  case "\$1" in -o) ziel=\$2; shift ;; -*I*) kopf=1 ;; http*) url=\$1 ;; esac; shift
done
if [ "\$kopf" = 1 ]; then printf 'HTTP/2 200\r\nlast-modified: %s\r\ncontent-length: 4718592000\r\n\r\n' "\$(cat "$T/stand")"; exit 0; fi
case "\$url" in
  *.md5) if [ -f "$T/md5-falsch" ]; then echo "00000000000000000000000000000000  germany-latest.osm.pbf"; else echo "\$(md5sum < "$T/quelle" | cut -d' ' -f1)  germany-latest.osm.pbf"; fi ;;
  *) [ -f "$T/download-fehler" ] && exit 22; cp "$T/quelle" "\$ziel" ;;
esac
STUB
cat > "$T/docker" <<STUB
#!/bin/sh
echo "\$*" >> "$T/aufrufe"
case "\$1" in
  info) [ -f "$T/ohne-docker" ] && exit 1; exit 0 ;;
  run) ;;
  *) echo "unerwartet: \$*" >&2; exit 9 ;;
esac
[ -f "$T/umwandeln-fehler" ] && exit 1
daten=\$(printf '%s\n' "\$@" | grep -m1 ':/daten\$' | cut -d: -f1)
[ -s "\$daten/adressen-quelle.osm.pbf" ] || { echo "Quelle fehlt" >&2; exit 1; }
python3 "$REPO/deploy/karte/adressen.py" --json "$REPO/tests/fixtures/karte/adressen.json" "\$daten/adressen.neu.sqlite" 2>/dev/null
STUB
chmod +x "$T/docker" "$T/curl"
export DOCKER="$T/docker" CURL="$T/curl" ADRESSEN_MIN=1 ADRESSEN_PLATZ_GB=0 AUS CODE
mkdir -p "$T/i/deploy/karte" && cp "$REPO/deploy/karte/adressen.py" "$REPO/deploy/karte/requirements.txt" "$T/i/deploy/karte/" && cd "$T/i" && touch .env docker-compose.yml

AUS=$(sh "$REPO/deploy/adressen-laden.sh" pruefen) && CODE=0 || CODE=$?
ok "prüfen: Stand und Größe der Quelle, freier Platz – nichts geladen" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Quelle: Mon, 26 Oct 2026 20:21:00 GMT, 4500 MB" && ! grep -q "^run" "$T/aufrufe" && [ ! -e daten-karte/adressen.sqlite ] && [ ! -e daten-karte/adressen-quelle.osm.pbf ]'

: > "$T/aufrufe"
AUS=$(sh "$REPO/deploy/adressen-laden.sh") && CODE=0 || CODE=$?
ok "laden: Verzeichnis geprüft und an seinem Platz, Stand vermerkt" '[ $CODE = 0 ] && echo "$AUS" | grep -q "6 Adressen" && [ -s daten-karte/adressen.sqlite ] && [ "$(cat daten-karte/adressen-stand.txt)" = "Mon, 26 Oct 2026 20:21:00 GMT" ]'
ok "laden: Quelldatei und Zwischenstände danach gelöscht" '[ ! -e daten-karte/adressen-quelle.osm.pbf ] && [ ! -e daten-karte/adressen.neu.sqlite ] && [ ! -e daten-karte/adressen.neu.sqlite.arbeit ]'
ok "laden: Datei für den Webserver lesbar (644)" '[ "$(stat -c %a daten-karte/adressen.sqlite)" = 644 ]'
ok "laden: Container mit fester Python-Fassung, pyosmium nur über Prüfsummen, ohne Abhängigkeiten" 'grep -q "python:3.12.14-slim-bookworm@sha256:" "$T/aufrufe" && grep -q -- "--require-hashes -r /werkzeug/requirements.txt" "$T/aufrufe" && grep -q -- "--no-deps --only-binary=:all:" "$T/aufrufe" && grep -q "deploy/karte:/werkzeug:ro" "$T/aufrufe"'
ok "laden: Quelle Deutschland von Geofabrik samt Prüfsumme" 'grep -q "https://download.geofabrik.de/europe/germany-latest.osm.pbf.md5" "$T/aufrufe"'

AUS=$(sh "$REPO/deploy/adressen-laden.sh") && CODE=0 || CODE=$?
ok "erneut laden: gleicher Stand – nichts zu tun" '[ $CODE = 0 ] && echo "$AUS" | grep -q "unverändert"'

alt=$(md5sum daten-karte/adressen.sqlite); export alt   # in den Prüfungen (eval) genutzt
echo 'Tue, 27 Oct 2026 20:21:00 GMT' > "$T/stand"
touch "$T/md5-falsch"
AUS=$(sh "$REPO/deploy/adressen-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "falsche Prüfsumme der Quelle: Abbruch, bisheriges Verzeichnis unverändert, Quelle gelöscht" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Prüfsumme der Quelle passt nicht" && [ "$(md5sum daten-karte/adressen.sqlite)" = "$alt" ] && [ ! -e daten-karte/adressen-quelle.osm.pbf ]'
rm -f "$T/md5-falsch"; touch "$T/umwandeln-fehler"
AUS=$(sh "$REPO/deploy/adressen-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "Umwandeln fehlgeschlagen: bisheriges Verzeichnis bleibt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "bisherige Verzeichnis bleibt" && [ "$(md5sum daten-karte/adressen.sqlite)" = "$alt" ] && [ ! -e daten-karte/adressen.neu.sqlite ]'
rm -f "$T/umwandeln-fehler"
AUS=$(ADRESSEN_MIN=1000 sh "$REPO/deploy/adressen-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "zu wenige Adressen: verworfen, bisheriges Verzeichnis bleibt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "unvollständig" && [ "$(md5sum daten-karte/adressen.sqlite)" = "$alt" ] && [ ! -e daten-karte/adressen.neu.sqlite ]'
touch "$T/download-fehler"
AUS=$(sh "$REPO/deploy/adressen-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "Download fehlgeschlagen: bisheriges Verzeichnis bleibt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Download fehlgeschlagen" && [ "$(md5sum daten-karte/adressen.sqlite)" = "$alt" ]'
rm -f "$T/download-fehler"
AUS=$(ADRESSEN_PLATZ_GB=999999 sh "$REPO/deploy/adressen-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "zu wenig Platz: Abbruch vor dem Laden" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Zu wenig freier Platz"'
touch "$T/ohne-netz"
AUS=$(sh "$REPO/deploy/adressen-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "Quelle nicht erreichbar: klarer Abbruch" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Quelle nicht erreichbar"'
rm -f "$T/ohne-netz"; touch "$T/ohne-docker"
AUS=$(sh "$REPO/deploy/adressen-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "ohne Docker: klarer Abbruch" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Docker ist nicht erreichbar"'
rm -f "$T/ohne-docker"
AUS=$(sh "$REPO/deploy/adressen-laden.sh") && CODE=0 || CODE=$?
ok "neuer Stand: Verzeichnis ersetzt, Stand vermerkt" '[ $CODE = 0 ] && [ "$(cat daten-karte/adressen-stand.txt)" = "Tue, 27 Oct 2026 20:21:00 GMT" ]'

AUS=$(sh "$REPO/deploy/adressen-laden.sh" entfernen) && CODE=0 || CODE=$?
ok "entfernen: Verzeichnis und Stand weg" '[ $CODE = 0 ] && [ ! -e daten-karte/adressen.sqlite ] && [ ! -e daten-karte/adressen-stand.txt ]'
AUS=$(cd "$T" && sh "$REPO/deploy/adressen-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "außerhalb des Installationsordners abgelehnt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Installationsordner"'
AUS=$(sh "$REPO/deploy/adressen-laden.sh" unsinn 2>&1) && CODE=0 || CODE=$?
ok "unbekannter Aufruf abgelehnt" '[ $CODE = 2 ]'

echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" = 0 ]
