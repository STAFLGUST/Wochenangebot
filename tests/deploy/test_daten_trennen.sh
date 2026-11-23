#!/bin/sh
# Test von deploy/daten-trennen.sh (ADR-007 Stufe 2) – mit Platzhaltern für docker, sichern.sh und chown in einem Wegwerf-Ordner;
# die eigentliche Trennung macht das echte deploy/daten_trennen.py (eigene Tests: tests/deploy/test_daten_trennen.py).
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
AUS=""; CODE=0
export AUS CODE
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
G='<?php http_response_code(404); exit; ?>'
printf '#!/bin/sh\necho "docker $*" >> "%s/aufrufe"\n' "$T" > "$T/docker"; chmod +x "$T/docker"
export DOCKER="$T/docker"
mkdir "$T/bin"; printf '#!/bin/sh\necho "chown $*" >> "%s/aufrufe"\nexit 0\n' "$T" > "$T/bin/chown"; chmod +x "$T/bin/chown"; export PATH="$T/bin:$PATH"
neu() {
  rm -rf "$T/i"; mkdir -p "$T/i/deploy/anmeldung" "$T/i/daten" "$T/i/regeln"; : > "$T/aufrufe"
  cp "$REPO/deploy/daten-trennen.sh" "$REPO/deploy/daten_trennen.py" "$REPO/deploy/datenbank.py" "$T/i/deploy/"
  cp "$REPO/regeln/datenverantwortung.toml" "$T/i/regeln/"
  cp "$REPO/deploy/anmeldung/docker-compose.anmeldung.yml" "$T/i/deploy/anmeldung/"
  printf '#!/bin/sh\necho "sichern $*" >> "%s/aufrufe"\n' "$T" > "$T/i/deploy/sichern.sh"
  printf 'DOMAIN=x\nCOMPOSE_FILE=docker-compose.yml:deploy/anmeldung/docker-compose.anmeldung.yml\n' > "$T/i/.env"
  printf '%s\n{"personen":[]}' "$G" > "$T/i/daten/hr-personal.php"
  printf '%s\n{"items":[]}' "$G" > "$T/i/daten/angebot.php"
}
lauf() { AUS=$(cd "$T/i" && sh deploy/daten-trennen.sh "$@" 2>&1) && CODE=0 || CODE=$?; }

neu; lauf status
ok "status: Plan, keine Sicherung, kein Stopp" '[ $CODE = 0 ] && echo "$AUS" | grep -q "hr-personal" && [ ! -s "$T/aufrufe" ] && [ ! -e "$T/i/daten-intern" ]'
neu; printf 'DOMAIN=x\n' > "$T/i/.env"; lauf trennen
ok "ohne getrennte Container (COMPOSE_FILE): Abbruch, nichts geändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "getrennten Containern" && [ ! -s "$T/aufrufe" ] && [ -f "$T/i/daten/hr-personal.php" ]'
neu; lauf trennen
ok "trennen: Sicherung → Stopp aller drei Dienste → trennen → Eigentümer → Start" '[ $CODE = 0 ] \
  && [ "$(sed -n 1p "$T/aufrufe")" = "sichern --jetzt" ] && [ "$(sed -n 2p "$T/aufrufe")" = "docker compose stop app app-mitarbeiter postausgang" ] \
  && grep -qx "chown -R -h 33:33 daten-intern" "$T/aufrufe" && [ "$(tail -1 "$T/aufrufe")" = "docker compose start app app-mitarbeiter postausgang" ]'
ok "trennen: Ergebnis (internes Dokument verschoben, Kennzeichen, nur Besitzer)" '[ -f "$T/i/daten-intern/hr-personal.php" ] && [ ! -e "$T/i/daten/hr-personal.php" ] \
  && [ -f "$T/i/daten/angebot.php" ] && [ -f "$T/i/daten/.daten-getrennt" ] && [ "$(stat -c %a "$T/i/daten-intern")" = 700 ]'
: > "$T/aufrufe"; lauf trennen
ok "trennen ein zweites Mal: nichts zu tun, kein Stopp" '[ $CODE = 0 ] && echo "$AUS" | grep -q "bereits getrennt" && [ ! -s "$T/aufrufe" ]'
lauf zusammenfuehren
ok "zusammenführen: wieder ein Ordner, Dienste gestoppt und gestartet" '[ $CODE = 0 ] && [ -f "$T/i/daten/hr-personal.php" ] && [ ! -e "$T/i/daten/.daten-getrennt" ] \
  && grep -qx "docker compose stop app app-mitarbeiter postausgang" "$T/aufrufe" && grep -qx "docker compose start app app-mitarbeiter postausgang" "$T/aufrufe"'
: > "$T/aufrufe"; lauf zusammenfuehren
ok "zusammenführen ohne Trennung: nichts zu tun" '[ $CODE = 0 ] && echo "$AUS" | grep -q "nicht getrennt" && [ ! -s "$T/aufrufe" ]'
# Abbruch beim Aufräumen des Zusammenführens (z. B. SSH getrennt): daten/ ohne Kennzeichen, daten-intern noch markiert
neu; lauf trennen
(cd "$T/i" && python3 -c "
import sys; sys.path.insert(0, 'deploy'); from pathlib import Path; import daten_trennen as dt
def abbruch(*a): raise OSError('Abbruch (Test)')
dt.dok_loeschen = abbruch
try: dt.zusammenfuehren(Path('daten').resolve(), Path('daten-intern').resolve(), dt.REGELN)
except OSError: pass")
ok "Testvoraussetzung: Zusammenführen beim Aufräumen abgebrochen" '[ ! -e "$T/i/daten/.daten-getrennt" ] && [ -f "$T/i/daten-intern/.daten-intern" ] && [ -f "$T/i/daten-intern/.zusammengefuehrt" ]'
: > "$T/aufrufe"; lauf zusammenfuehren
ok "zusammenführen erneut: vollendet (ohne neue Sicherung, die an den Kennzeichen scheiterte), Dienste gestoppt und gestartet" '[ $CODE = 0 ] && echo "$AUS" | grep -q "vollendet" \
  && ! grep -q "^sichern" "$T/aufrufe" && grep -qx "docker compose stop app app-mitarbeiter postausgang" "$T/aufrufe" && grep -qx "docker compose start app app-mitarbeiter postausgang" "$T/aufrufe" \
  && [ -f "$T/i/daten/hr-personal.php" ] && [ ! -e "$T/i/daten-intern/.daten-intern" ] && [ ! -e "$T/i/daten-intern/.zusammengefuehrt" ]'
# Abbruch zwischen Vermerk und Umschalten (daten/ noch gekennzeichnet): die Anwendung lief getrennt weiter und speicherte innen
# Neueres – erneut zusammenführen sichert neu und bricht mit Meldung ab, statt die innere Fassung beim Aufräumen zu löschen
neu; lauf trennen
(cd "$T/i" && python3 -c "
import sys; sys.path.insert(0, 'deploy'); from pathlib import Path; import daten_trennen as dt
def abbruch(*a): raise OSError('Abbruch (Test)')
dt.aufraeumen = abbruch
try: dt.zusammenfuehren(Path('daten').resolve(), Path('daten-intern').resolve(), dt.REGELN)
except OSError: pass")
ok "Testvoraussetzung: Abbruch direkt nach dem Vermerk, beide Kennzeichen stehen" '[ -f "$T/i/daten/.daten-getrennt" ] && [ -f "$T/i/daten-intern/.daten-intern" ] && [ -f "$T/i/daten-intern/.zusammengefuehrt" ]'
printf '%s\n{"personen":[{"name":"nach dem Abbruch"}]}' "$G" > "$T/i/daten-intern/hr-personal.php"
: > "$T/aufrufe"; lauf zusammenfuehren
ok "… erneut zusammenführen: neue Sicherung, Abbruch wegen abweichender Fassung, innere Fassung bleibt" '[ $CODE = 1 ] && [ "$(sed -n 1p "$T/aufrufe")" = "sichern --jetzt" ] \
  && ! echo "$AUS" | grep -q "vollendet" && echo "$AUS" | grep -q "verschiedenem Inhalt" && grep -q "nach dem Abbruch" "$T/i/daten-intern/hr-personal.php" \
  && [ -f "$T/i/daten-intern/.daten-intern" ] && [ -f "$T/i/daten/.daten-getrennt" ] && ! grep -q "compose start" "$T/aufrufe"'
# Kennzeichen in daten/ von außen entfernt (ohne Vermerk): nicht „nichts zu tun“, sondern Abbruch, Anwendung bleibt gestoppt
neu; lauf trennen; rm "$T/i/daten/.daten-getrennt"
: > "$T/aufrufe"; lauf zusammenfuehren
ok "Kennzeichen nur in daten-intern: keine Meldung läuft unverändert weiter, sondern Abbruch ohne Änderung" '[ $CODE = 1 ] && ! echo "$AUS" | grep -q "unverändert weiter" \
  && echo "$AUS" | grep -q "Nicht automatisch reparieren" && [ -f "$T/i/daten-intern/hr-personal.php" ] && ! grep -q "compose start" "$T/aufrufe"'
neu; printf '%s\n{"x":1}' "$G" > "$T/i/daten-fremd.php"; mkdir -p "$T/i/daten-intern"; printf '%s\n{"x":1}' "$G" > "$T/i/daten-intern/fremd.php"; lauf trennen
ok "Fehler beim Trennen: Anwendung bleibt gestoppt (kein Start), Hinweis" '[ $CODE = 1 ] && echo "$AUS" | grep -q "bleibt absichtlich gestoppt" \
  && grep -q "compose stop" "$T/aufrufe" && ! grep -q "compose start" "$T/aufrufe" && [ -f "$T/i/daten/hr-personal.php" ]'
neu; lauf vielleicht
ok "unbekannte Aktion abgelehnt" '[ $CODE = 2 ]'
echo "daten-trennen.sh: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
