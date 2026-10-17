#!/bin/sh
# Tägliche Datensicherung des Ordners daten/ – wird von aktualisieren.sh aufgerufen (höchstens 1× pro Tag).
# Sofort sichern:   sh /opt/wochenangebot/deploy/sichern.sh --jetzt
# Jede Sicherung wird direkt nach dem Erstellen probeweise entpackt und geprüft (alle Datendateien lesbar).
# Ablage: /opt/wochenangebot/sicherungen (nur für root lesbar, nicht über das Web erreichbar), die letzten 30 Stände.
set -eu
cd "$(dirname "$0")/.."
BASIS=$(pwd)
ZIEL="$BASIS/sicherungen"
BEHALTEN=30
STATUS="$BASIS/daten/sicherung.php"
GUARD='<?php http_response_code(404); exit; ?>'

mkdir -p "$ZIEL"
chmod 700 "$ZIEL"
if [ "${1:-}" != "--jetzt" ]; then
  # schon eine Sicherung in den letzten 23 Stunden → nichts tun; nach einem Fehlschlag frühestens nach 1 Stunde erneut
  [ -n "$(find "$ZIEL" -maxdepth 1 -name 'daten-*.tar.gz' -mmin -1380 | head -1)" ] && exit 0
  [ -n "$(find "$ZIEL" -maxdepth 1 -name '.letzter-fehler' -mmin -60 | head -1)" ] && exit 0
fi
[ -d "$BASIS/daten" ] || { echo "Ordner daten/ fehlt"; exit 1; }

status() { # ok datei groesse dateien fehler
  ANZ=$(find "$ZIEL" -maxdepth 1 -name 'daten-*.tar.gz' | wc -l)
  printf '%s\n{"t":"%s","ok":%s,"datei":"%s","groesse":%s,"dateien":%s,"fehler":%s,"anzahl":%s,"behalten":%s}' \
    "$GUARD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" "$5" "$ANZ" "$BEHALTEN" > "$STATUS.tmp"
  chown 33:33 "$STATUS.tmp" 2>/dev/null || true
  chmod 644 "$STATUS.tmp"
  mv "$STATUS.tmp" "$STATUS"
}
fehler() { touch "$ZIEL/.letzter-fehler"; status false "" 0 0 1; echo "Datensicherung fehlgeschlagen: $1"; exit 1; }

FREI=$(df -Pk "$ZIEL" | awk 'NR==2 {print $4}')
[ "${FREI:-0}" -gt 204800 ] || fehler "zu wenig Speicherplatz"

STAMP=$(date -u +%Y-%m-%d_%H%M%S)
DATEI="$ZIEL/daten-$STAMP.tar.gz"
tar czf "$DATEI.tmp" -C "$BASIS/daten" --exclude='./geo' --exclude='*.tmp' --exclude='./.*.lock' --exclude='./sicherung.php' . || fehler "Archiv konnte nicht erstellt werden"

# Wiederherstellungstest: in einen leeren Ordner entpacken und jede Datendatei prüfen
PRUEF=$(mktemp -d)
trap 'rm -rf "$PRUEF"' EXIT
tar xzf "$DATEI.tmp" -C "$PRUEF" || { rm -f "$DATEI.tmp"; fehler "Archiv nicht lesbar"; }
QUELLE=$(cd "$BASIS/daten" && find . -name '*.php' ! -path './geo/*' ! -name 'sicherung.php' | wc -l)
DATEIEN=$(find "$PRUEF" -name '*.php' | wc -l)
FEHLER=0
if command -v python3 >/dev/null 2>&1; then
  FEHLER=$(python3 "$BASIS/deploy/sicherung-pruefen.py" "$PRUEF")
fi
[ "$DATEIEN" -ge "$QUELLE" ] || FEHLER=$((FEHLER + QUELLE - DATEIEN))

mv "$DATEI.tmp" "$DATEI"
chmod 600 "$DATEI"
ls -1t "$ZIEL"/daten-*.tar.gz | tail -n +$((BEHALTEN + 1)) | xargs -r rm -f
GROESSE=$(stat -c %s "$DATEI")
if [ "$FEHLER" -eq 0 ]; then
  rm -f "$ZIEL/.letzter-fehler"
  status true "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" 0
  echo "Datensicherung erstellt und geprüft: $(basename "$DATEI") ($DATEIEN Dateien)"
else
  touch "$ZIEL/.letzter-fehler"
  status false "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" "$FEHLER"
  echo "Datensicherung erstellt, aber $FEHLER Datei(en) fehlerhaft: $(basename "$DATEI")"
  exit 1
fi
