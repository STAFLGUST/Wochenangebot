#!/bin/sh
# Test von deploy/karte-laden.sh – mit Platzhaltern für docker und curl, in einem Wegwerf-Ordner (lädt nichts herunter).
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
# docker: „extract … /daten/<datei>“ schreibt eine Datei (Größe aus $T/groesse, Kopf PMTiles), --dry-run schreibt nichts
cat > "$T/docker" <<STUB
#!/bin/sh
echo "\$*" >> "$T/aufrufe"
case "\$1" in
  info) [ -f "$T/ohne-docker" ] && exit 1; exit 0 ;;
  run) ;;
  *) echo "unerwartet: \$*" >&2; exit 9 ;;
esac
daten=\$(printf '%s\n' "\$@" | grep -m1 ':/daten' | cut -d: -f1)
case "\$*" in
  *" extract "*"--dry-run"*) echo "Probelauf: 5,4 GB" ;;
  *" extract "*)
    [ -f "$T/laden-fehler" ] && exit 1
    ziel=\$(printf '%s\n' "\$@" | grep -m1 '^/daten/' | sed 's|^/daten/||')
    # mit \$T/verweis: der Lauf legt statt der Datei einen Verweis nach außerhalb an (wie ein übernommenes Werkzeug)
    [ -f "$T/verweis" ] && { ln -sfn "$T/opfer" "\$daten/\$ziel"; exit 0; }
    { printf 'PMTiles'; head -c "\$(cat "$T/groesse")" /dev/zero; } > "\$daten/\$ziel" ;;
  *" show "*) [ -f "$T/show-fehler" ] && exit 1; exit 0 ;;
  *) echo "unerwartet: \$*" >&2; exit 9 ;;
esac
STUB
cat > "$T/curl" <<STUB
#!/bin/sh
echo '[{"key":"20261020.pmtiles"},{"key":"20261026.pmtiles"},{"key":"irgendwas.txt"}]'
STUB
chmod +x "$T/docker" "$T/curl"
export DOCKER="$T/docker" CURL="$T/curl" KARTE_MIN_MB=1 KARTE_PLATZ_GB=0 AUS CODE
mkdir -p "$T/i/deploy/karte" && cp "$REPO/deploy/karte/deutschland.geojson" "$T/i/deploy/karte/" && cd "$T/i" && touch .env docker-compose.yml
echo 2097152 > "$T/groesse"   # 2 MB

AUS=$(sh "$REPO/deploy/karte-laden.sh" pruefen) && CODE=0 || CODE=$?
ok "prüfen: neuester Stand aus der Liste, nur Probelauf, nichts geschrieben" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Kartenstand: 20261026" && grep -q -- "--dry-run" "$T/aufrufe" && [ ! -e daten-karte/karte.pmtiles ]'
ok "prüfen: Ausschnitt Deutschland, Zoomstufe 15, Werkzeug mit fester Prüfsumme" 'grep -q -- "--region=/region/deutschland.geojson --maxzoom=15" "$T/aufrufe" && grep -q "go-pmtiles:v1.31.2@sha256:" "$T/aufrufe" && grep -q "https://build.protomaps.com/20261026.pmtiles" "$T/aufrufe"'

: > "$T/aufrufe"
AUS=$(sh "$REPO/deploy/karte-laden.sh") && CODE=0 || CODE=$?
ok "laden: Datei geprüft und an ihren Platz, Stand vermerkt, keine Zwischendatei übrig" '[ $CODE = 0 ] && [ "$(head -c 7 daten-karte/karte.pmtiles)" = PMTiles ] && [ "$(cat daten-karte/stand.txt)" = 20261026.pmtiles ] && [ ! -e daten-karte/karte.neu.pmtiles ] && grep -q " show /daten/karte.neu.pmtiles" "$T/aufrufe"'
ok "laden: Datei für den Webserver lesbar (644)" '[ "$(stat -c %a daten-karte/karte.pmtiles)" = 644 ]'

AUS=$(sh "$REPO/deploy/karte-laden.sh") && CODE=0 || CODE=$?
ok "erneut laden: gleicher Stand – nichts zu tun" '[ $CODE = 0 ] && echo "$AUS" | grep -q "unverändert"'

alt=$(md5sum daten-karte/karte.pmtiles); export alt   # in den Prüfungen (eval) genutzt
echo 10 > "$T/groesse"   # unvollständig
AUS=$(KARTE_MIN_MB=1 KARTE_STAND=20261027.pmtiles sh "$REPO/deploy/karte-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "zu kleine neue Datei: verworfen, bisherige Karte unverändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "unvollständig" && [ "$(md5sum daten-karte/karte.pmtiles)" = "$alt" ] && [ ! -e daten-karte/karte.neu.pmtiles ]'

echo 2097152 > "$T/groesse"; touch "$T/show-fehler"
AUS=$(KARTE_STAND=20261027.pmtiles sh "$REPO/deploy/karte-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "nicht lesbare neue Datei: verworfen, bisherige Karte bleibt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht lesbar" && [ "$(md5sum daten-karte/karte.pmtiles)" = "$alt" ]'
rm -f "$T/show-fehler"; touch "$T/laden-fehler"
AUS=$(KARTE_STAND=20261027.pmtiles sh "$REPO/deploy/karte-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "Download fehlgeschlagen: bisherige Karte bleibt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "bisherige Karte bleibt" && [ "$(md5sum daten-karte/karte.pmtiles)" = "$alt" ]'
rm -f "$T/laden-fehler"

# daten-karte ist im Lade-Container beschreibbar: dort angelegte Verweise dürfen root nie umlenken (wie tests/deploy/test_sichern.sh)
echo ORIGINAL > "$T/opfer"; chmod 600 "$T/opfer"; touch "$T/verweis"
AUS=$(KARTE_STAND=20261028.pmtiles sh "$REPO/deploy/karte-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "Verweis statt neuer Karte: Abbruch, fremde Datei unverändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "kein echtes Ergebnis" \
  && [ "$(cat "$T/opfer")" = ORIGINAL ] && [ "$(stat -c %a "$T/opfer")" = 600 ] && [ "$(md5sum daten-karte/karte.pmtiles)" = "$alt" ]'
rm -f "$T/verweis" daten-karte/karte.neu.pmtiles
rm -f daten-karte/stand.txt daten-karte/karte.pmtiles
ln -s "$T/opfer" daten-karte/stand.txt; ln -s "$T/opfer2" daten-karte/karte.pmtiles
AUS=$(KARTE_STAND=20261028.pmtiles sh "$REPO/deploy/karte-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "Karte und Stand folgen keinem Verweis in daten-karte (Ziele unverändert, Verweise ersetzt, Inhalt nicht gelesen)" '[ $CODE = 0 ] \
  && echo "$AUS" | grep -q "(bisher: keiner)" && ! echo "$AUS" | grep -q ORIGINAL \
  && [ "$(cat "$T/opfer")" = ORIGINAL ] && [ "$(stat -c %a "$T/opfer")" = 600 ] && [ ! -e "$T/opfer2" ] \
  && [ ! -L daten-karte/stand.txt ] && [ ! -L daten-karte/karte.pmtiles ] && [ "$(cat daten-karte/stand.txt)" = 20261028.pmtiles ] \
  && [ "$(head -c 7 daten-karte/karte.pmtiles)" = PMTiles ] && [ -z "$(ls -A . | grep "^\.stand\.")" ]'
alt=$(md5sum daten-karte/karte.pmtiles)

AUS=$(KARTE_PLATZ_GB=999999 KARTE_STAND=20261027.pmtiles sh "$REPO/deploy/karte-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "zu wenig Platz: Abbruch vor dem Laden" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Zu wenig freier Platz"'
AUS=$(KARTE_STAND="../x" sh "$REPO/deploy/karte-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "ungültiger Stand abgelehnt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Kein gültiger Kartenstand"'
touch "$T/ohne-docker"
AUS=$(sh "$REPO/deploy/karte-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "ohne Docker: klarer Abbruch" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Docker ist nicht erreichbar"'
rm -f "$T/ohne-docker"

# Zweite Karte „herkunft“ (Südamerika und Neuseeland, Container-Import): eigene Region, Datei und Stand, die Detailkarte bleibt
cp "$REPO/deploy/karte/herkunft.geojson" deploy/karte/
: > "$T/aufrufe"
AUS=$(sh "$REPO/deploy/karte-laden.sh" pruefen herkunft) && CODE=0 || CODE=$?
ok "herkunft prüfen: Region Südamerika und Neuseeland, Zoomstufe 14, nichts geschrieben" '[ $CODE = 0 ] && grep -q -- "--region=/region/herkunft.geojson --maxzoom=14" "$T/aufrufe" && [ ! -e daten-karte/herkunft.pmtiles ] && echo "$AUS" | grep -q "Laden mit: sh .*laden herkunft" && echo "$AUS" | grep -q "Zoomstufe: 14 (bisher: keine)"'
alt=$(md5sum daten-karte/karte.pmtiles)
AUS=$(sh "$REPO/deploy/karte-laden.sh" laden herkunft) && CODE=0 || CODE=$?
ok "herkunft laden: eigene Datei, eigener Stand, Zoomstufe vermerkt, Detailkarte unberührt" '[ $CODE = 0 ] && [ "$(head -c 7 daten-karte/herkunft.pmtiles)" = PMTiles ] && [ "$(cat daten-karte/herkunft-stand.txt)" = 20261026.pmtiles ] && [ "$(cat daten-karte/herkunft-zoom.txt)" = 14 ] && [ "$(md5sum daten-karte/karte.pmtiles)" = "$alt" ] && [ "$(stat -c %a daten-karte/herkunft.pmtiles)" = 644 ] && [ ! -e daten-karte/herkunft.neu.pmtiles ]'
: > "$T/aufrufe"
AUS=$(sh "$REPO/deploy/karte-laden.sh" laden herkunft) && CODE=0 || CODE=$?
ok "herkunft erneut laden: gleicher Stand und gleiche Zoomstufe – nichts zu tun" '[ $CODE = 0 ] && echo "$AUS" | grep -q "unverändert" && ! grep -q " extract " "$T/aufrufe"'
AUS=$(KARTE_HERKUNFT_ZOOM=10 sh "$REPO/deploy/karte-laden.sh" pruefen herkunft) && CODE=0 || CODE=$?
ok "herkunft: Zoomstufe einstellbar, der Hinweis zum Laden nennt sie, unsinnige abgelehnt" '[ $CODE = 0 ] && grep -q -- "--maxzoom=10" "$T/aufrufe" && echo "$AUS" | grep -q "Laden mit: KARTE_HERKUNFT_ZOOM=10 sh .*laden herkunft" && ! KARTE_HERKUNFT_ZOOM="12 --x" sh "$REPO/deploy/karte-laden.sh" pruefen herkunft >/dev/null 2>&1'
: > "$T/aufrufe"
AUS=$(KARTE_HERKUNFT_ZOOM=12 sh "$REPO/deploy/karte-laden.sh" laden herkunft) && CODE=0 || CODE=$?
ok "herkunft: andere Zoomstufe lädt auch bei gleichem Kartenstand neu" '[ $CODE = 0 ] && grep -q -- " extract .*--maxzoom=12" "$T/aufrufe" && [ "$(cat daten-karte/herkunft-zoom.txt)" = 12 ] && echo "$AUS" | grep -q "Zoomstufe 12"'
: > "$T/aufrufe"
AUS=$(KARTE_STAND=20261027.pmtiles sh "$REPO/deploy/karte-laden.sh" laden herkunft) && CODE=0 || CODE=$?
ok "herkunft: Aktualisierung ohne Angabe bleibt bei der gemerkten Zoomstufe" '[ $CODE = 0 ] && grep -q -- " extract .*--maxzoom=12" "$T/aufrufe" && [ "$(cat daten-karte/herkunft-stand.txt)" = 20261027.pmtiles ] && [ "$(cat daten-karte/herkunft-zoom.txt)" = 12 ]'
rm daten-karte/herkunft-zoom.txt; : > "$T/aufrufe"   # Karte aus der Fassung ohne Vermerk der Zoomstufe
AUS=$(KARTE_STAND=20261027.pmtiles sh "$REPO/deploy/karte-laden.sh" laden herkunft) && CODE=0 || CODE=$?
ok "herkunft: Karte ohne vermerkte Zoomstufe wird einmal neu geladen (Stufe 14)" '[ $CODE = 0 ] && grep -q -- " extract .*--maxzoom=14" "$T/aufrufe" && [ "$(cat daten-karte/herkunft-zoom.txt)" = 14 ]'
echo geheim > "$T/opfer"; rm daten-karte/herkunft-zoom.txt; ln -s "$T/opfer" daten-karte/herkunft-zoom.txt
AUS=$(sh "$REPO/deploy/karte-laden.sh" pruefen herkunft 2>&1) && CODE=0 || CODE=$?
ok "herkunft: untergeschobener Verweis als Zoom-Vermerk wird nicht gelesen" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Zoomstufe: 14 (bisher: keine)" && ! echo "$AUS" | grep -q geheim'
AUS=$(sh "$REPO/deploy/karte-laden.sh" entfernen herkunft) && CODE=0 || CODE=$?
ok "herkunft entfernen: nur die Herkunftskarte, mit beiden Vermerken" '[ $CODE = 0 ] && [ ! -e daten-karte/herkunft.pmtiles ] && [ ! -e daten-karte/herkunft-stand.txt ] && [ ! -e daten-karte/herkunft-zoom.txt ] && [ ! -L daten-karte/herkunft-zoom.txt ] && [ -e daten-karte/karte.pmtiles ] && [ "$(cat "$T/opfer")" = geheim ]'
AUS=$(sh "$REPO/deploy/karte-laden.sh" laden mond 2>&1) && CODE=0 || CODE=$?
ok "unbekannte Karte abgelehnt" '[ $CODE = 2 ]'

AUS=$(sh "$REPO/deploy/karte-laden.sh" entfernen) && CODE=0 || CODE=$?
ok "entfernen: Datei und Stand weg" '[ $CODE = 0 ] && [ ! -e daten-karte/karte.pmtiles ] && [ ! -e daten-karte/stand.txt ]'
AUS=$(cd "$T" && sh "$REPO/deploy/karte-laden.sh" 2>&1) && CODE=0 || CODE=$?
ok "außerhalb des Installationsordners abgelehnt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Installationsordner"'
AUS=$(sh "$REPO/deploy/karte-laden.sh" unsinn 2>&1) && CODE=0 || CODE=$?
ok "unbekannter Aufruf abgelehnt" '[ $CODE = 2 ]'

echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" = 0 ]
