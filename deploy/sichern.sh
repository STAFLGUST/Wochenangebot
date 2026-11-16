#!/bin/sh
# Tägliche Datensicherung des Ordners daten/ (nach der Datentrennung, ADR-007 Stufe 2, zusätzlich daten-intern/ als intern-*.tar.gz).
# Zeitsteuerung: eigener systemd-Timer (deploy/sicherung-einrichten.sh). Solange dieser nicht eingerichtet ist,
# ruft aktualisieren.sh das Skript auf (höchstens 1× pro Tag).
# Sofort sichern:   sh /opt/wochenangebot/deploy/sichern.sh --jetzt
#
# Jede Sicherung wird direkt nach dem Erstellen probeweise entpackt und geprüft (alle Datendateien lesbar).
# Dateiablage (dateien/ in daten/ bzw. nach der Trennung in daten-intern/, hochgeladene Dateien wie QM-Dokumente): nicht im
# Archiv, sondern je Lauf als Stand sicherungen/dateien-<daten|intern>/<Zeit>/ mit festen Verweisen auf den vorigen Stand
# (deploy/dateien_sichern.py) – Platz für einen Bestand plus die Änderungen. Geprüft wird, dass jede Datei, auf die die
# gesicherten Daten verweisen, im Stand liegt, dazu eine Stichprobe mit SHA-256. Fehlt das Werkzeug (Sicherung vor dem
# Release: Skript des neuen Commits, übrige Dateien in deploy/ noch im alten Stand), bleibt die Dateiablage im Archiv.
# Vor dem Sichern wird der Platz geprüft (neue Dateien, dreimal die übrigen Daten, 5 GB Reserve); reicht er nicht, bricht
# die Sicherung mit Meldung im Status ab.
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
DSW="$BASIS/deploy/dateien_sichern.py"
DSF="$ZIEL/.dateisicherung-fehler"
[ -f "$DSW" ] || DSW=""
D_ANZAHL=0; D_GROESSE=0; D_NEU=0; D_STAENDE=0; D_BELEGT=0
ANM_DATEI=""
ANM_MELDUNG=""
ANM_GRUND=""
INTERN_DATEI=""
KC_COMPOSE=${WA_KC_COMPOSE:-docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml}

status() { # ok datei groesse dateien fehler inhalt_geprueft meldung
  ANZ=$(find "$ZIEL" -maxdepth 1 -name 'daten-*.tar.gz' 2>/dev/null | wc -l)
  printf '%s\n{"t":"%s","ok":%s,"datei":"%s","groesse":%s,"dateien":%s,"fehler":%s,"inhalt":%s,"anzahl":%s,"behalten":%s,"meldung":"%s","datensaetze":%s,"speicher":"%s","anmeldung":"%s","anmeldung_datei":"%s","intern_datei":"%s","dateien_anzahl":%s,"dateien_groesse":%s,"dateien_neu":%s,"dateien_staende":%s,"dateien_belegt":%s}' \
    "$GUARD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" "$5" "$6" "$ANZ" "$BEHALTEN" "$7" "$DATENSAETZE" "$SPEICHER" "$ANMELDUNG" "$ANM_DATEI" "${INTERN_DATEI##*/}" \
    "$D_ANZAHL" "$D_GROESSE" "$D_NEU" "$D_STAENDE" "$D_BELEGT" \
    | status_schreiben
}
# daten/ ist im Container beschreibbar: dort angelegte Verweise dürfen root nie umlenken. Deshalb entsteht die Datei
# außerhalb von daten/ (Ordner des Echtbetriebs, nur root) und ersetzt den Eintrag in daten/ nur per Umbenennen
# (folgt keinem Verweis, ersetzt ihn). Kein Schreiben, chown oder chmod auf einen Namen in daten/.
status_schreiben() {
  ST_TMP=$(mktemp "$BASIS/.status.XXXXXX") || return 0
  cat > "$ST_TMP" || { rm -f "$ST_TMP"; return 0; }
  chown 33:33 "$ST_TMP" 2>/dev/null || true
  chmod 644 "$ST_TMP"
  mv -fT "$ST_TMP" "$STATUS" || rm -f "$ST_TMP"
}
melden() { # ok|fail
  [ -n "$HC_URL" ] || return 0
  if [ "$1" = ok ]; then curl -fsS -m 10 --retry 3 "$HC_URL" >/dev/null 2>&1 || true
  else curl -fsS -m 10 --retry 3 "$HC_URL/fail" >/dev/null 2>&1 || true; fi
}
aufraeumen() {
  RC=$?
  # shellcheck disable=SC2086  # Listen von Wegwerf-Ordnern (mktemp, ohne Leerzeichen)
  [ -n "$SNAP" ] && rm -rf $SNAP
  # shellcheck disable=SC2086
  [ -n "$PRUEF" ] && rm -rf $PRUEF
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

STAMP=$(date -u +%Y-%m-%d_%H%M%S)
# ablagen: je Dateiablage „<quelle>:<ziel>“ (Pfade ohne Leerzeichen); daten-intern nur nach der Datentrennung
ablagen() {
  [ -n "$DSW" ] || return 0
  for A in daten:daten daten-intern:intern; do
    [ "${A%%:*}" = daten-intern ] && [ ! -f "$BASIS/daten-intern/.daten-intern" ] && continue
    [ -d "$BASIS/${A%%:*}/dateien" ] && echo "$BASIS/${A%%:*}/dateien:$ZIEL/dateien-${A##*:}"
  done
  return 0
}
ds_grund() { tail -1 "$DSF" 2>/dev/null | tr -d '"\\\000-\037' | cut -c1-200; }
dateien_aufbauen() {
  for A in $(ablagen); do
    N=$(python3 "$DSW" aufbauen "${A%%:*}" "${A#*:}" "$STAMP" 2>"$DSF") || fehler "$(ds_grund)"
    D_NEU=$((D_NEU + N))
  done
}

# Platz: neue Dateien der Ablage + dreimal die übrigen Daten (Abzug der Datenbank, Archiv, Probe-Entpacken) + 5 GB Reserve.
# Unter 5 GB frei warnt der Reiter System (Speicherplatz); die Sicherung soll den Server nie unter diese Schwelle drücken.
gb() { awk -v k="$1" 'BEGIN { printf "%.1f", k / 1048576 }' | tr . ,; }
NEU_KB=0
for A in $(ablagen); do
  rm -rf "${A#*:}"/*.tmp   # Reste eines abgebrochenen Laufs
  N=$(python3 "$DSW" bedarf "${A%%:*}" "${A#*:}" 2>"$DSF") || fehler "$(ds_grund)"
  NEU_KB=$((NEU_KB + N / 1024))
done
AUSSER=""; [ -n "$DSW" ] && AUSSER=--exclude=dateien
# shellcheck disable=SC2046,SC2086  # optionaler Ordner und Ausschluss ohne Leerzeichen
DATEN_KB=$(du -sk $AUSSER "$BASIS/daten" $([ -d "$BASIS/daten-intern" ] && echo "$BASIS/daten-intern") | awk '{s += $1} END {print s + 0}')
NOETIG=$((NEU_KB + 3 * DATEN_KB + 5 * 1048576))
FREI=$(df -Pk "$ZIEL" | awk 'NR==2 {print $4}')
[ "${FREI:-0}" -ge "$NOETIG" ] || fehler "zu wenig Speicherplatz: $(gb "${FREI:-0}") GB frei, nötig $(gb "$NOETIG") GB (neue Dateien $(gb "$NEU_KB") GB, Daten 3 × $(gb "$DATEN_KB") GB, Reserve 5 GB)"

dateien_aufbauen
DATEIEN=0
FEHLER=0
INHALT=true
# sichere_ordner <ordner> <name>: Archiv <name>-<Zeit>.tar.gz (SQLite: aus einem geprüften Abzug), probeweise entpacken und jede
# Datendatei prüfen; zählt DATEIEN, FEHLER und DATENSAETZE weiter, behält je Name die letzten $BEHALTEN Stände
sichere_ordner() {
  O_ORDNER=$1; O_NAME=$2
  O_DATEI="$ZIEL/$O_NAME-$STAMP.tar.gz"
  O_QUELLE="$O_ORDNER"
  if [ -f "$O_ORDNER/.sqlite-active" ]; then
    O_SNAP=$(mktemp -d); SNAP="$SNAP $O_SNAP"
    python3 "$BASIS/deploy/datenbank.py" snapshot "$O_ORDNER" --output "$O_SNAP/data" >/dev/null || fehler "Datenbank-Sicherung fehlgeschlagen ($O_NAME)"
    O_QUELLE="$O_SNAP/data"
  fi
  # shellcheck disable=SC2086  # ohne Werkzeug für die Dateiablage bleibt sie im Archiv
  tar czf "$O_DATEI.tmp" -C "$O_QUELLE" ${DSW:+--exclude=./dateien} --exclude='./geo' --exclude='*.tmp' --exclude='./.*.lock' --exclude='./sicherung.php' --exclude='./mail-schluessel.php' . || { rm -f "$O_DATEI.tmp"; fehler "Archiv konnte nicht erstellt werden ($O_NAME)"; }
  # Wiederherstellungstest: in einen leeren Ordner entpacken und jede Datendatei prüfen
  O_PRUEF=$(mktemp -d); PRUEF="$PRUEF $O_PRUEF"
  tar xzf "$O_DATEI.tmp" -C "$O_PRUEF" || { rm -f "$O_DATEI.tmp"; fehler "Archiv nicht lesbar ($O_NAME)"; }
  O_QZAHL=$(cd "$O_QUELLE" && find . -name '*.php' ! -path './geo/*' ! -name 'sicherung.php' ! -name 'mail-schluessel.php' | wc -l)
  O_DATEIEN=$(find "$O_PRUEF" -name '*.php' | wc -l)
  O_FEHLER=0
  if command -v python3 >/dev/null 2>&1; then
    O_FEHLER=$(python3 "$BASIS/deploy/sicherung-pruefen.py" "$O_PRUEF")
  elif command -v php >/dev/null 2>&1; then
    O_FEHLER=$(php "$BASIS/deploy/sicherung-pruefen.php" "$O_PRUEF")
  else
    INHALT=false
  fi
  case "$O_FEHLER" in ''|*[!0-9]*) O_FEHLER=1 ;; esac
  # Anzahl gesicherter Datensätze: Dokumente in der Datenbank bzw. Datendateien
  if [ -f "$O_PRUEF/.sqlite-active" ]; then
    SPEICHER=sqlite
    O_SAETZE=$(python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('SELECT COUNT(*) FROM documents').fetchone()[0])" "$O_PRUEF/.sqlite/store.sqlite" 2>/dev/null || echo 0)
  else
    O_SAETZE=$(find "$O_PRUEF" -name '*.php' ! -name 'index.php' ! -name 'deployment.php' | wc -l)
  fi
  case "$O_SAETZE" in ''|*[!0-9]*) O_SAETZE=0 ;; esac
  [ "$O_DATEIEN" -ge "$O_QZAHL" ] || O_FEHLER=$((O_FEHLER + O_QZAHL - O_DATEIEN))
  mv "$O_DATEI.tmp" "$O_DATEI"
  chmod 600 "$O_DATEI"
  ls -1t "$ZIEL"/"$O_NAME"-*.tar.gz | tail -n +$((BEHALTEN + 1)) | xargs -r rm -f
  DATEIEN=$((DATEIEN + O_DATEIEN)); FEHLER=$((FEHLER + O_FEHLER)); DATENSAETZE=$((DATENSAETZE + O_SAETZE))
}
DATEI="$ZIEL/daten-$STAMP.tar.gz"
sichere_ordner "$BASIS/daten" daten
# Getrennte Daten (ADR-007 Stufe 2, deploy/daten-trennen.sh): interne Dokumente liegen in daten-intern/ – eigenes Archiv
# intern-<Zeit>.tar.gz, gleich geprüft. Wiederherstellen: daten-*.tar.gz nach daten/, intern-*.tar.gz nach daten-intern/.
# Maßgeblich ist das Kennzeichen in daten-intern/ (dort kann die Kundenseite nicht schreiben): sonst könnte ein entferntes
# Kennzeichen in daten/ die internen Daten still aus der Sicherung nehmen. Beide Kennzeichen müssen zusammenpassen.
if [ -f "$BASIS/daten-intern/.daten-intern" ] || [ -f "$BASIS/daten/.daten-getrennt" ]; then
  [ -f "$BASIS/daten-intern/.daten-intern" ] || fehler "Daten sind getrennt, daten-intern/ fehlt aber oder ist nicht markiert"
  [ -f "$BASIS/daten/.daten-getrennt" ] || fehler "daten-intern/ ist markiert, in daten/ fehlt das Kennzeichen (sh deploy/daten-trennen.sh status)"
  sichere_ordner "$BASIS/daten-intern" intern
  INTERN_DATEI="$ZIEL/intern-$STAMP.tar.gz"
fi
# Dateien, die während des Archivs hinzukamen, ergänzen; dann gegen die entpackten Archive prüfen und abschließen
if [ -n "$(ablagen)" ]; then
  dateien_aufbauen
  # shellcheck disable=SC2046,SC2086  # Listen ohne Leerzeichen
  ERG=$(python3 "$DSW" abschliessen "$BEHALTEN" "$STAMP" $(ablagen | sed 's/^[^:]*://') --daten $PRUEF 2>"$DSF") || fehler "$(ds_grund)"
  # shellcheck disable=SC2086
  set -- $ERG; D_ANZAHL=$1; D_GROESSE=$2; D_STAENDE=$3; D_BELEGT=$4
fi

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
  echo "Datensicherung erstellt und geprüft: $(basename "$DATEI")${INTERN_DATEI:+ und $(basename "$INTERN_DATEI")} ($DATENSAETZE Datensätze, $([ "$SPEICHER" = sqlite ] && echo Datenbank || echo Dateien))$([ "$ANMELDUNG" = ok ] && echo "; Anmeldung: $ANM_DATEI")$([ "$D_STAENDE" -gt 0 ] && echo "; Dateiablage: $D_ANZAHL Dateien, $((D_NEU / 1048576)) MB neu kopiert")"
else
  touch "$ZIEL/.letzter-fehler"
  status false "$(basename "$DATEI")" "$GROESSE" "$DATEIEN" "$FEHLER" "$INHALT" "$FEHLER Datei(en) fehlerhaft${ANM_MELDUNG:+; $ANM_MELDUNG}"
  melden fail
  echo "Datensicherung erstellt, aber $FEHLER Datei(en) fehlerhaft: $(basename "$DATEI")"
  exit 1
fi
