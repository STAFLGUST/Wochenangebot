#!/bin/sh
# Tägliche Datensicherung des Ordners daten/.
# Zeitsteuerung: eigener systemd-Timer (deploy/sicherung-einrichten.sh). Solange dieser nicht eingerichtet ist,
# ruft aktualisieren.sh das Skript auf (höchstens 1× pro Tag).
# Sofort sichern:   sh /opt/wochenangebot/deploy/sichern.sh --jetzt
#
# Jede Sicherung wird direkt nach dem Erstellen probeweise entpackt und geprüft (alle Datendateien lesbar).
# Nicht gesichert wird der Schlüssel für das im Eingabebereich hinterlegte Postfach-Passwort (mail-schluessel.php):
# Sicherungen enthalten das Passwort damit nur verschlüsselt; nach einer Wiederherstellung auf neuem Server muss es
# unter Verwaltung → E-Mail neu eingegeben werden.
# Ablage: /opt/wochenangebot/sicherungen (nur für root lesbar, nicht über das Web erreichbar), die letzten 30 Stände.
# Zentrale Anmeldung: läuft Keycloak (deploy/anmeldung), wird zusätzlich dessen Datenbank gesichert
# (anmeldung-<Zeit>.dump, pg_dump im Container, Inhalt geprüft). Enthält Passwort-Hashes und Einmalcode-Geheimnisse –
# gleicher Schutz wie die Geschäftsdaten. Rücksicherung üben: deploy/anmeldung/ruecksicherung-probe.sh,
# Ablauf: docs/plattform/inbetriebnahme-anmeldung.md.
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
SNAP=""
DATENSAETZE=0
SPEICHER=dateien
ANMELDUNG=aus          # aus (nicht in Betrieb) | ok | fehler
ANM_DATEI=""
ANM_MELDUNG=""
ANM_GRUND=""
KC_COMPOSE=${WA_KC_COMPOSE:-docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml}

status() { # ok datei groesse dateien fehler inhalt_geprueft meldung
  ANZ=$(find "$ZIEL" -maxdepth 1 -name 'daten-*.tar.gz' 2>/dev/null | wc -l)
  printf '%s\n{"t":"%s","ok":%s,"datei":"%s","groesse":%s,"dateien":%s,"fehler":%s,"inhalt":%s,"anzahl":%s,"behalten":%s,"meldung":"%s","datensaetze":%s,"speicher":"%s","anmeldung":"%s","anmeldung_datei":"%s"}' \
    "$GUARD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" "$5" "$6" "$ANZ" "$BEHALTEN" "$7" "$DATENSAETZE" "$SPEICHER" "$ANMELDUNG" "$ANM_DATEI" > "$STATUS.tmp" || return 0
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
  [ -n "$SNAP" ] && rm -rf "$SNAP"
  [ -n "$PRUEF" ] && rm -rf "$PRUEF"
  rm -f "$ZIEL"/anmeldung-*.dump.tmp "$ZIEL"/anmeldung-*.dump.fehler.tmp 2>/dev/null
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
QUELLORDNER="$BASIS/daten"
if [ -f "$BASIS/daten/.sqlite-active" ]; then
  SNAP=$(mktemp -d)
  python3 "$BASIS/deploy/datenbank.py" snapshot "$BASIS/daten" --output "$SNAP/data" >/dev/null || fehler "Datenbank-Sicherung fehlgeschlagen"
  QUELLORDNER="$SNAP/data"
fi
tar czf "$DATEI.tmp" -C "$QUELLORDNER" --exclude='./geo' --exclude='*.tmp' --exclude='./.*.lock' --exclude='./sicherung.php' --exclude='./mail-schluessel.php' . || { rm -f "$DATEI.tmp"; fehler "Archiv konnte nicht erstellt werden"; }

# Wiederherstellungstest: in einen leeren Ordner entpacken und jede Datendatei prüfen
PRUEF=$(mktemp -d)
tar xzf "$DATEI.tmp" -C "$PRUEF" || { rm -f "$DATEI.tmp"; fehler "Archiv nicht lesbar"; }
QUELLE=$(cd "$QUELLORDNER" && find . -name '*.php' ! -path './geo/*' ! -name 'sicherung.php' ! -name 'mail-schluessel.php' | wc -l)
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
# Anzahl gesicherter Datensätze: Dokumente in der Datenbank bzw. Datendateien
if [ -f "$PRUEF/.sqlite-active" ]; then
  SPEICHER=sqlite
  DATENSAETZE=$(python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('SELECT COUNT(*) FROM documents').fetchone()[0])" "$PRUEF/.sqlite/store.sqlite" 2>/dev/null || echo 0)
else
  DATENSAETZE=$(find "$PRUEF" -name '*.php' ! -name 'index.php' ! -name 'deployment.php' | wc -l)
fi
case "$DATENSAETZE" in ''|*[!0-9]*) DATENSAETZE=0 ;; esac
[ "$DATEIEN" -ge "$QUELLE" ] || FEHLER=$((FEHLER + QUELLE - DATEIEN))

mv "$DATEI.tmp" "$DATEI"
chmod 600 "$DATEI"
ls -1t "$ZIEL"/daten-*.tar.gz | tail -n +$((BEHALTEN + 1)) | xargs -r rm -f

# ── Zentrale Anmeldung: Keycloak-Datenbank, sobald sie läuft oder laut .env in Betrieb ist ──
anmeldung_sichern() {
  KC_DUMP="$ZIEL/anmeldung-$STAMP.dump"
  # Die Datenbank verlangt auch im Container ein Passwort (scram-sha-256): es kommt aus der Umgebung des Containers
  # (POSTGRES_PASSWORD), nie über die Befehlszeile. Grund eines Fehlers landet gekürzt in der Statusmeldung.
  # shellcheck disable=SC2086,SC2016  # KC_COMPOSE ist bewusst ein Befehl mit Argumenten; $POSTGRES_PASSWORD wertet der Container aus
  if ! $KC_COMPOSE exec -T keycloak-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -U keycloak -d keycloak --format=custom' > "$KC_DUMP.tmp" 2>"$KC_DUMP.fehler.tmp"; then
    ANM_GRUND=$(tail -1 "$KC_DUMP.fehler.tmp" | tr -d '"\\\000-\037' | cut -c1-160); return 1
  fi
  # Prüfung: Archiv lesbar und enthält die Konten (Tabelle user_entity mit Daten)
  # shellcheck disable=SC2086
  $KC_COMPOSE exec -T keycloak-db pg_restore --list < "$KC_DUMP.tmp" 2>/dev/null | grep -q 'TABLE DATA public user_entity' || return 1
  mv "$KC_DUMP.tmp" "$KC_DUMP"; chmod 600 "$KC_DUMP"
  ls -1t "$ZIEL"/anmeldung-*.dump | tail -n +$((BEHALTEN + 1)) | xargs -r rm -f
  ANM_DATEI=$(basename "$KC_DUMP")
}
if [ -f "$BASIS/deploy/anmeldung/docker-compose.anmeldung.yml" ] && [ -d "$BASIS/daten-anmeldung" ]; then
  # shellcheck disable=SC2086
  if [ -n "$($KC_COMPOSE ps -q keycloak-db 2>/dev/null)" ]; then
    if anmeldung_sichern; then ANMELDUNG=ok; else ANMELDUNG=fehler; ANM_MELDUNG="Sicherung der Anmeldung (Keycloak) fehlgeschlagen${ANM_GRUND:+: $ANM_GRUND}"; fi
  elif grep -q '^COMPOSE_FILE=.*anmeldung' "$BASIS/.env" 2>/dev/null; then
    ANMELDUNG=fehler; ANM_MELDUNG="Anmeldung (Keycloak) in Betrieb, Datenbank läuft aber nicht – nicht gesichert"
  fi
fi
rm -f "$ZIEL"/anmeldung-*.dump.tmp "$ZIEL"/anmeldung-*.dump.fehler.tmp
GROESSE=$(stat -c %s "$DATEI")
FERTIG=1
if [ "$FEHLER" -eq 0 ] && [ "$ANMELDUNG" = fehler ]; then
  touch "$ZIEL/.letzter-fehler"
  status false "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" 0 "$INHALT" "$ANM_MELDUNG"
  melden fail
  echo "Datensicherung erstellt und geprüft: $(basename "$DATEI"); aber: $ANM_MELDUNG"
  exit 1
elif [ "$FEHLER" -eq 0 ]; then
  rm -f "$ZIEL/.letzter-fehler"
  if [ "$INHALT" = true ]; then
    status true "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" 0 true ""
  else
    status true "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" 0 false "Inhalt nicht geprüft (kein Python/PHP verfügbar)"
  fi
  melden ok
  echo "Datensicherung erstellt und geprüft: $(basename "$DATEI") ($DATENSAETZE Datensätze, $([ "$SPEICHER" = sqlite ] && echo Datenbank || echo Dateien))$([ "$ANMELDUNG" = ok ] && echo "; Anmeldung: $ANM_DATEI")"
else
  touch "$ZIEL/.letzter-fehler"
  status false "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" "$FEHLER" "$INHALT" "$FEHLER Datei(en) fehlerhaft${ANM_MELDUNG:+; $ANM_MELDUNG}"
  melden fail
  echo "Datensicherung erstellt, aber $FEHLER Datei(en) fehlerhaft: $(basename "$DATEI")"
  exit 1
fi
