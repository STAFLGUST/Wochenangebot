#!/bin/sh
# Tägliche Datensicherung des Ordners daten/ (nach der Datentrennung, ADR-007 Stufe 2, zusätzlich daten-intern/ als intern-*.tar.gz).
# Zeitsteuerung: eigener systemd-Timer (deploy/sicherung-einrichten.sh). Solange dieser nicht eingerichtet ist,
# ruft aktualisieren.sh das Skript auf (höchstens 1× pro Tag).
# Sofort sichern:   sh /opt/wochenangebot/deploy/sichern.sh --jetzt
#
# Ablauf: Platz prüfen, Archive und Stand der Dateiablage als .tmp bauen, Archive probeweise entpacken und prüfen, den Stand
# gegen die Verweise der Archive prüfen. Erst wenn alles stimmt, werden Archive und Stand gemeinsam festgeschrieben und die
# Aufbewahrung angewandt (rotieren). Ein Fehler entfernt alles dieses Laufs; ältere Sicherungen bleiben unangetastet.
# Dateiablage (dateien/ in daten/ bzw. nach der Trennung in daten-intern/, z. B. QM-Dokumente): nicht im Archiv, sondern je
# Lauf ein Stand sicherungen/dateien/<Zeit>/ mit festen Verweisen auf den vorigen (deploy/dateien_sichern.py; beim Release die
# Fassung des neuen Commits, deploy/.dateien_sichern-release.py). Fehlen Dateien, auf die die Daten verweisen, in Ablage und
# Stand, ist das nur eine Warnung (Liste sicherungen/.dateien-fehlend). Platzbedarf: docs/entwickler/08-betrieb.md.
# Nicht gesichert wird der Schlüssel für das im Eingabebereich hinterlegte Postfach-Passwort (mail-schluessel.php):
# Sicherungen enthalten das Passwort damit nur verschlüsselt; nach einer Wiederherstellung auf neuem Server muss es
# unter Verwaltung → E-Mail neu eingegeben werden.
# Ablage: /opt/wochenangebot/sicherungen (nur für root lesbar, nicht über das Web erreichbar). Aufbewahrung: rotieren().
# Zwei Läufe gleichzeitig verhindert eine Sperre (sicherungen/.sperre); der zweite endet sofort mit Fehler.
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
BEHALTEN=30            # so viele Läufe bleiben mindestens, auch bei verstellter Uhr (rotieren)
STATUS="$BASIS/daten/sicherung.php"
GUARD='<?php http_response_code(404); exit; ?>'
HC_URL=$(sed -n 's/^HC_SICHERUNG_URL=//p' "$BASIS/.env" 2>/dev/null | head -1 | tr -d '"'"'"' ')
FERTIG=0
STAMP=""
ARBEIT=""
DATENSAETZE=0
SPEICHER=dateien
ANMELDUNG=aus          # aus (nicht in Betrieb) | ok | fehler
ABLAGE_JSON=null
ANM_DATEI=""
ANM_MELDUNG=""
INTERN_DATEI=""
KC_COMPOSE=${WA_KC_COMPOSE:-docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml}
DSW="$BASIS/deploy/.dateien_sichern-release.py"
[ -f "$DSW" ] || DSW="$BASIS/deploy/dateien_sichern.py"
[ -f "$DSW" ] || DSW=""

status() { # ok datei groesse dateien fehler inhalt_geprueft meldung
  ANZ=$(find "$ZIEL" -maxdepth 1 -name 'daten-*.tar.gz' 2>/dev/null | wc -l)
  printf '%s\n{"t":"%s","ok":%s,"datei":"%s","groesse":%s,"dateien":%s,"fehler":%s,"inhalt":%s,"anzahl":%s,"behalten":%s,"meldung":"%s","datensaetze":%s,"speicher":"%s","anmeldung":"%s","anmeldung_datei":"%s","intern_datei":"%s","ablage":%s}' \
    "$GUARD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" "$5" "$6" "$ANZ" "$BEHALTEN" "$7" "$DATENSAETZE" "$SPEICHER" "$ANMELDUNG" "$ANM_DATEI" "$INTERN_DATEI" "$ABLAGE_JSON" \
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
grund() { tail -1 "$1" 2>/dev/null | tr -d '"\\\000-\037' | cut -c1-"$2"; }   # letzte Zeile einer Fehlerausgabe, für JSON entschärft
aufraeumen() {
  RC=$?
  [ -z "$ARBEIT" ] || rm -rf "$ARBEIT"
  # alles dieses Laufs, was noch nicht festgeschrieben ist (STAMP erst mit der Sperre gesetzt)
  [ -z "$STAMP" ] || rm -rf "$ZIEL/dateien/$STAMP.tmp" "$ZIEL"/*-"$STAMP".tar.gz.tmp "$ZIEL/anmeldung-$STAMP".dump*.tmp
  if [ "$FERTIG" -eq 0 ] && [ "$RC" -ne 0 ]; then   # unerwarteter Abbruch: Fehler sichtbar machen
    touch "$ZIEL/.letzter-fehler" 2>/dev/null || true
    status false "" 0 0 1 false "Abbruch (Code $RC)"
    melden fail
    echo "Datensicherung abgebrochen (Code $RC)"
  fi
}
trap aufraeumen EXIT
fehler() { FERTIG=1; touch "$ZIEL/.letzter-fehler" 2>/dev/null || true; status false "" 0 0 "${2:-1}" false "$1"; melden fail; echo "Datensicherung fehlgeschlagen: $1"; exit 1; }

mkdir -p "$ZIEL"
chmod 700 "$ZIEL"
if [ "${1:-}" != "--jetzt" ]; then
  # schon eine Sicherung in den letzten 23 Stunden → nichts tun; nach einem Fehlschlag frühestens nach 1 Stunde erneut
  if [ -n "$(find "$ZIEL" -maxdepth 1 -name 'daten-*.tar.gz' -mmin -1380 | head -1)" ]; then FERTIG=1; exit 0; fi
  if [ -n "$(find "$ZIEL" -maxdepth 1 -name '.letzter-fehler' -mmin -60 | head -1)" ]; then FERTIG=1; exit 0; fi
fi
exec 9>"$ZIEL/.sperre"
flock -n 9 || { FERTIG=1; echo "Datensicherung läuft bereits – dieser Aufruf sichert nicht"; exit 1; }
STAMP=$(date -u +%Y-%m-%d_%H%M%S)
rm -rf "$ZIEL"/dateien/*.tmp "$ZIEL"/*.tmp   # Reste abgebrochener Läufe (unter der Sperre läuft kein anderer)
ARBEIT=$(mktemp -d)
DSF="$ARBEIT/werkzeug-fehler"
AUSSER="$ARBEIT/ausser"   # nicht im Archiv und nicht im Platzbedarf (tar und du lesen dieselbe Liste)
printf '%s\n' ./geo ./sicherung.php ./mail-schluessel.php '*.tmp' './.*.lock' > "$AUSSER"
# shortcut: ohne Werkzeug bleibt die Dateiablage im Archiv (nur die Release-Sicherung, die #378 einspielt: altes deploy/); nach dem ersten Release mit Werkzeug entfernen
if [ -n "$DSW" ]; then echo ./dateien >> "$AUSSER"; export WA_SNAPSHOT_OHNE_DATEIEN=1; fi
ds() { [ -z "$DSW" ] || python3 "$DSW" "$@" 2>"$DSF"; }
[ -d "$BASIS/daten" ] || fehler "Ordner daten/ fehlt"

# Getrennte Daten (ADR-007 Stufe 2, deploy/daten-trennen.sh): interne Dokumente und die Dateiablage liegen in daten-intern/
# (wie ablage_wurzel() in lib/dateiablage.php); eigenes Archiv intern-<Zeit>.tar.gz. Maßgeblich ist das Kennzeichen in
# daten-intern/ (dort kann die Kundenseite nicht schreiben): sonst könnte ein entferntes Kennzeichen in daten/ die internen
# Daten still aus der Sicherung nehmen. Beide Kennzeichen müssen zusammenpassen.
INTERN=""
if [ -f "$BASIS/daten-intern/.daten-intern" ] || [ -f "$BASIS/daten/.daten-getrennt" ]; then
  [ -f "$BASIS/daten-intern/.daten-intern" ] || fehler "Daten sind getrennt, daten-intern/ fehlt aber oder ist nicht markiert"
  [ -f "$BASIS/daten/.daten-getrennt" ] || fehler "daten-intern/ ist markiert, in daten/ fehlt das Kennzeichen (sh deploy/daten-trennen.sh status)"
  INTERN="$BASIS/daten-intern"
fi
ABLAGE="${INTERN:-$BASIS/daten}/dateien"

# Platz: neue Dateien der Ablage + dreimal die übrigen Daten (Abzug der Datenbank, Archiv, Probe-Entpacken) + 5 GB Reserve
# (Warnschwelle „Speicherplatz“ im Reiter System). Begründung: docs/entwickler/08-betrieb.md.
gb() { awk -v k="$1" 'BEGIN { printf "%.1f", k / 1048576 }' | tr . ,; }
NEU=$(ds bedarf "$ABLAGE" "$ZIEL/dateien") || fehler "$(grund "$DSF" 200)"
NEU_KB=$((${NEU:-0} / 1024))
DATEN_KB=0
for O in "$BASIS/daten" ${INTERN:+"$INTERN"}; do DATEN_KB=$((DATEN_KB + $(cd "$O" && du -sk -X "$AUSSER" . | cut -f1))); done
NOETIG=$((NEU_KB + 3 * DATEN_KB + 5 * 1048576))
FREI=$(df -Pk "$ZIEL" | awk 'NR==2 {print $4}')
[ "${FREI:-0}" -ge "$NOETIG" ] || fehler "zu wenig Speicherplatz: $(gb "${FREI:-0}") GB frei, nötig $(gb "$NOETIG") GB (neue Dateien $(gb "$NEU_KB") GB, Daten 3 × $(gb "$DATEN_KB") GB, Reserve 5 GB)"

ds aufbauen "$ABLAGE" "$ZIEL/dateien" "$STAMP" || fehler "$(grund "$DSF" 200)"
DATEIEN=0
FEHLER=0
INHALT=true
# sichere_ordner <ordner> <name>: Archiv <name>-<Zeit>.tar.gz.tmp (SQLite: aus einem geprüften Abzug), probeweise nach
# $ARBEIT/pruef-<name> entpacken und jede Datendatei prüfen; zählt DATEIEN, FEHLER und DATENSAETZE weiter
sichere_ordner() {
  O_ORDNER=$1; O_NAME=$2
  O_DATEI="$ZIEL/$O_NAME-$STAMP.tar.gz.tmp"
  O_QUELLE="$O_ORDNER"
  if [ -f "$O_ORDNER/.sqlite-active" ]; then
    O_QUELLE="$ARBEIT/abzug-$O_NAME"
    python3 "$BASIS/deploy/datenbank.py" snapshot "$O_ORDNER" --output "$O_QUELLE" >/dev/null || fehler "Datenbank-Sicherung fehlgeschlagen ($O_NAME)"
  fi
  tar czf "$O_DATEI" -C "$O_QUELLE" -X "$AUSSER" . || fehler "Archiv konnte nicht erstellt werden ($O_NAME)"
  # Wiederherstellungstest: in einen leeren Ordner entpacken und jede Datendatei prüfen
  O_PRUEF="$ARBEIT/pruef-$O_NAME"; mkdir "$O_PRUEF"
  tar xzf "$O_DATEI" -C "$O_PRUEF" || fehler "Archiv nicht lesbar ($O_NAME)"
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
  DATEIEN=$((DATEIEN + O_DATEIEN)); FEHLER=$((FEHLER + O_FEHLER)); DATENSAETZE=$((DATENSAETZE + O_SAETZE))
}
sichere_ordner "$BASIS/daten" daten
[ -z "$INTERN" ] || sichere_ordner "$INTERN" intern
[ "$FEHLER" -eq 0 ] || fehler "$FEHLER Datei(en) im Archiv fehlerhaft – nicht gesichert, ältere Sicherungen bleiben" "$FEHLER"
# Stand um Dateien ergänzen, die während der Archive hinzukamen, und gegen die Verweise der entpackten Archive prüfen
ds pruefen "$ABLAGE" "$ZIEL/dateien" "$STAMP" "$ARBEIT"/pruef-* || fehler "$(grund "$DSF" 200)"
WARNUNG=$(grund "$DSF" 300)

# rotieren: Aufbewahrung, gemeinsam für Archive, Keycloak-Sicherungen und Stände der Dateiablage derselben Zeit. Es bleiben
# alle Läufe der letzten 7 Tage, der letzte Lauf jedes Tages der letzten 30 Tage und immer die $BEHALTEN neuesten Läufe
# (eine verstellte Uhr löscht so nie alles). Maßgeblich sind die Zeiten der Datenarchive.
rotieren() {
  B=$(for F in "$ZIEL"/daten-*.tar.gz; do F=${F##*/daten-}; echo "${F%.tar.gz}"; done | sort -r \
    | awk -v w="$(date -u -d '7 days ago' +%Y-%m-%d_%H%M%S)" -v m="$(date -u -d '30 days ago' +%Y-%m-%d_%H%M%S)" -v n="$BEHALTEN" \
        'NR <= n || $0 >= w || ($0 >= m && substr($0, 1, 10) != tag) { print } { tag = substr($0, 1, 10) }')
  for F in "$ZIEL"/daten-*.tar.gz "$ZIEL"/intern-*.tar.gz "$ZIEL"/anmeldung-*.dump "$ZIEL"/dateien/*; do
    Z=${F##*/}; Z=${Z#daten-}; Z=${Z#intern-}; Z=${Z#anmeldung-}; Z=${Z%.tar.gz}; Z=${Z%.dump}
    case $Z in ????-??-??_??????) case $B in *"$Z"*) ;; *) rm -rf "$F" ;; esac ;; esac
  done
}
for F in "$ZIEL"/*-"$STAMP".tar.gz.tmp; do chmod 600 "$F"; mv "$F" "${F%.tmp}"; done
[ ! -d "$ZIEL/dateien/$STAMP.tmp" ] || mv "$ZIEL/dateien/$STAMP.tmp" "$ZIEL/dateien/$STAMP"
rotieren
INTERN_DATEI=${INTERN:+intern-$STAMP.tar.gz}
if [ -n "$DSW" ]; then ABLAGE_JSON=$(ds abschliessen "$ZIEL/dateien" "$STAMP") || fehler "$(grund "$DSF" 200)"; fi

# ── Zentrale Anmeldung: Keycloak-Datenbank, sobald sie läuft oder laut .env in Betrieb ist ──
anmeldung_sichern() {
  KC_DUMP="$ZIEL/anmeldung-$STAMP.dump"
  # Die Datenbank verlangt auch im Container ein Passwort (scram-sha-256): es kommt aus der Umgebung des Containers
  # (POSTGRES_PASSWORD), nie über die Befehlszeile. Grund eines Fehlers landet gekürzt in der Statusmeldung.
  # shellcheck disable=SC2086,SC2016  # KC_COMPOSE ist bewusst ein Befehl mit Argumenten; $POSTGRES_PASSWORD wertet der Container aus
  if ! $KC_COMPOSE exec -T keycloak-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -U keycloak -d keycloak --format=custom' > "$KC_DUMP.tmp" 2>"$KC_DUMP.fehler.tmp"; then
    ANM_GRUND=$(grund "$KC_DUMP.fehler.tmp" 160); return 1
  fi
  # Prüfung: Archiv lesbar und enthält die Konten (Tabelle user_entity mit Daten)
  # shellcheck disable=SC2086
  $KC_COMPOSE exec -T keycloak-db pg_restore --list < "$KC_DUMP.tmp" 2>/dev/null | grep -q 'TABLE DATA public user_entity' || return 1
  mv "$KC_DUMP.tmp" "$KC_DUMP"; chmod 600 "$KC_DUMP"
  ANM_DATEI=$(basename "$KC_DUMP")
}
ANM_GRUND=""
if [ -f "$BASIS/deploy/anmeldung/docker-compose.anmeldung.yml" ] && [ -d "$BASIS/daten-anmeldung" ]; then
  # shellcheck disable=SC2086
  if [ -n "$($KC_COMPOSE ps -q keycloak-db 2>/dev/null)" ]; then
    if anmeldung_sichern; then ANMELDUNG=ok; else ANMELDUNG=fehler; ANM_MELDUNG="Sicherung der Anmeldung (Keycloak) fehlgeschlagen${ANM_GRUND:+: $ANM_GRUND}"; fi
  elif grep -q '^COMPOSE_FILE=.*anmeldung' "$BASIS/.env" 2>/dev/null; then
    ANMELDUNG=fehler; ANM_MELDUNG="Anmeldung (Keycloak) in Betrieb, Datenbank läuft aber nicht – nicht gesichert"
  fi
fi
DATEI="daten-$STAMP.tar.gz"
GROESSE=$(stat -c %s "$ZIEL/$DATEI")
FERTIG=1
if [ "$ANMELDUNG" = fehler ]; then
  touch "$ZIEL/.letzter-fehler"
  status false "$DATEI" "$GROESSE" "$DATEIEN" 0 "$INHALT" "$ANM_MELDUNG${WARNUNG:+; $WARNUNG}"
  melden fail
  echo "Datensicherung erstellt und geprüft: $DATEI; aber: $ANM_MELDUNG"
  exit 1
fi
rm -f "$ZIEL/.letzter-fehler"
[ "$INHALT" = true ] || WARNUNG="Inhalt nicht geprüft (kein Python/PHP verfügbar)${WARNUNG:+; $WARNUNG}"
status true "$DATEI" "$GROESSE" "$DATEIEN" 0 "$INHALT" "$WARNUNG"
melden ok
echo "Datensicherung erstellt und geprüft: $DATEI${INTERN_DATEI:+ und $INTERN_DATEI} ($DATENSAETZE Datensätze, $([ "$SPEICHER" = sqlite ] && echo Datenbank || echo Dateien))$([ "$ANMELDUNG" = ok ] && echo "; Anmeldung: $ANM_DATEI")${WARNUNG:+; Warnung: $WARNUNG}"
