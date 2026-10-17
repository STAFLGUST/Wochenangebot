#!/bin/sh
# Tägliche Datensicherung des Ordners daten/.
# Zeitsteuerung: eigener systemd-Timer (deploy/sicherung-einrichten.sh). Solange dieser nicht eingerichtet ist,
# ruft aktualisieren.sh das Skript auf (höchstens 1× pro Tag).
# Sofort sichern:   sh /opt/wochenangebot/deploy/sichern.sh --jetzt
#
# Jede Sicherung wird direkt nach dem Erstellen probeweise entpackt und geprüft (alle Datendateien lesbar).
# Ablage: /opt/wochenangebot/sicherungen (nur für root lesbar, nicht über das Web erreichbar), die letzten 30 Stände.
# Status: daten/sicherung.php (Anzeige im Eingabebereich unter „Sicherheit“). Jeder Abbruch – auch ein
# unerwarteter – hinterlässt dort einen Fehlerstatus. Optional meldet das Skript Erfolg/Fehler an einen
# Totmannschalter-Dienst: HC_SICHERUNG_URL=https://… in .env (bei Fehler wird „/fail“ angehängt).
set -eu
cd "$(dirname "$0")/.."
BASIS=$(pwd)
ZIEL="$BASIS/sicherungen"
BEHALTEN=30
STATUS="$BASIS/daten/sicherung.php"
GUARD='<?php http_response_code(404); exit; ?>'
HC_URL=$(sed -n 's/^HC_SICHERUNG_URL=//p' "$BASIS/.env" 2>/dev/null | head -1 | tr -d '"'"'"' ')
FERTIG=0
PRUEF=""

status() { # ok datei groesse dateien fehler inhalt_geprueft meldung
  ANZ=$(find "$ZIEL" -maxdepth 1 -name 'daten-*.tar.gz' 2>/dev/null | wc -l)
  printf '%s\n{"t":"%s","ok":%s,"datei":"%s","groesse":%s,"dateien":%s,"fehler":%s,"inhalt":%s,"anzahl":%s,"behalten":%s,"meldung":"%s"}' \
    "$GUARD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" "$5" "$6" "$ANZ" "$BEHALTEN" "$7" > "$STATUS.tmp" || return 0
  chown 33:33 "$STATUS.tmp" 2>/dev/null || true
  chmod 644 "$STATUS.tmp"
  mv "$STATUS.tmp" "$STATUS"
}
melden() { # ok|fail
  [ -n "$HC_URL" ] || return 0
  if [ "$1" = ok ]; then curl -fsS -m 10 --retry 3 "$HC_URL" >/dev/null 2>&1 || true
  else curl -fsS -m 10 --retry 3 "$HC_URL/fail" >/dev/null 2>&1 || true; fi
}
aufraeumen() {
  RC=$?
  [ -n "$PRUEF" ] && rm -rf "$PRUEF"
  if [ "$FERTIG" -eq 0 ] && [ "$RC" -ne 0 ]; then   # unerwarteter Abbruch: Fehler sichtbar machen
    touch "$ZIEL/.letzter-fehler" 2>/dev/null || true
    status false "" 0 0 1 false "Abbruch (Code $RC)"
    melden fail
    echo "Datensicherung abgebrochen (Code $RC)"
  fi
}
trap aufraeumen EXIT
fehler() { FERTIG=1; touch "$ZIEL/.letzter-fehler" 2>/dev/null || true; status false "" 0 0 1 false "$1"; melden fail; echo "Datensicherung fehlgeschlagen: $1"; exit 1; }

mkdir -p "$ZIEL"
chmod 700 "$ZIEL"
if [ "${1:-}" != "--jetzt" ]; then
  # schon eine Sicherung in den letzten 23 Stunden → nichts tun; nach einem Fehlschlag frühestens nach 1 Stunde erneut
  if [ -n "$(find "$ZIEL" -maxdepth 1 -name 'daten-*.tar.gz' -mmin -1380 | head -1)" ]; then FERTIG=1; exit 0; fi
  if [ -n "$(find "$ZIEL" -maxdepth 1 -name '.letzter-fehler' -mmin -60 | head -1)" ]; then FERTIG=1; exit 0; fi
fi
[ -d "$BASIS/daten" ] || fehler "Ordner daten/ fehlt"

FREI=$(df -Pk "$ZIEL" | awk 'NR==2 {print $4}')
[ "${FREI:-0}" -gt 204800 ] || fehler "zu wenig Speicherplatz"

STAMP=$(date -u +%Y-%m-%d_%H%M%S)
DATEI="$ZIEL/daten-$STAMP.tar.gz"
tar czf "$DATEI.tmp" -C "$BASIS/daten" --exclude='./geo' --exclude='*.tmp' --exclude='./.*.lock' --exclude='./sicherung.php' . || { rm -f "$DATEI.tmp"; fehler "Archiv konnte nicht erstellt werden"; }

# Wiederherstellungstest: in einen leeren Ordner entpacken und jede Datendatei prüfen
PRUEF=$(mktemp -d)
tar xzf "$DATEI.tmp" -C "$PRUEF" || { rm -f "$DATEI.tmp"; fehler "Archiv nicht lesbar"; }
QUELLE=$(cd "$BASIS/daten" && find . -name '*.php' ! -path './geo/*' ! -name 'sicherung.php' | wc -l)
DATEIEN=$(find "$PRUEF" -name '*.php' | wc -l)
FEHLER=0
INHALT=true
if command -v python3 >/dev/null 2>&1; then
  FEHLER=$(python3 "$BASIS/deploy/sicherung-pruefen.py" "$PRUEF")
elif command -v php >/dev/null 2>&1; then
  FEHLER=$(php "$BASIS/deploy/sicherung-pruefen.php" "$PRUEF")
else
  INHALT=false
fi
case "$FEHLER" in ''|*[!0-9]*) FEHLER=1 ;; esac
[ "$DATEIEN" -ge "$QUELLE" ] || FEHLER=$((FEHLER + QUELLE - DATEIEN))

mv "$DATEI.tmp" "$DATEI"
chmod 600 "$DATEI"
ls -1t "$ZIEL"/daten-*.tar.gz | tail -n +$((BEHALTEN + 1)) | xargs -r rm -f
GROESSE=$(stat -c %s "$DATEI")
FERTIG=1
if [ "$FEHLER" -eq 0 ]; then
  rm -f "$ZIEL/.letzter-fehler"
  if [ "$INHALT" = true ]; then
    status true "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" 0 true ""
  else
    status true "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" 0 false "Inhalt nicht geprüft (kein Python/PHP verfügbar)"
  fi
  melden ok
  echo "Datensicherung erstellt und geprüft: $(basename "$DATEI") ($DATEIEN Dateien)"
else
  touch "$ZIEL/.letzter-fehler"
  status false "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" "$FEHLER" "$INHALT" "$FEHLER Datei(en) fehlerhaft"
  melden fail
  echo "Datensicherung erstellt, aber $FEHLER Datei(en) fehlerhaft: $(basename "$DATEI")"
  exit 1
fi
