#!/bin/sh
# Test von deploy/passwort-zuruecksetzen.php (läuft im App-Container, nicht über das Web erreichbar): neuen Administrator
# anlegen, Passwort eines vorhandenen Mitarbeiters zurücksetzen, Mitarbeiter „ohne Anmeldung“ (zugang=false) ablehnen.
# Wegwerf-Datenordner, keine echten Daten.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
AUS=""
export AUS CODE HASH1 HASH2
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
mkdir -p "$T/daten"
WERKZEUG="$REPO/deploy/passwort-zuruecksetzen.php"
NUTZER="$T/daten/nutzer.php"
PW1='Erstes-Passwort-11'
PW2='Zweites-Passwort-22'
lauf() { AUS=$(DATA_DIR="$T/daten" php "$WERKZEUG" "$@" 2>&1) && CODE=0 || CODE=$?; }
feld() { php -r '$j=json_decode(preg_replace("~^<\?php.*\n~", "", file_get_contents($argv[1])), true); echo json_encode($j["users"][0][$argv[2]] ?? null);' "$NUTZER" "$1"; }

lauf chef "$PW1" --neu
ok "--neu legt einen Administrator mit Passwortwechsel an" '[ $CODE = 0 ] && [ "$(feld role)" = "\"admin\"" ] && [ "$(feld mustChange)" = true ] && [ "$(feld active)" = true ]'
HASH1=$(feld hash)
lauf unbekannt "$PW1"
ok "unbekanntes Konto ohne --neu abgelehnt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht gefunden"'
lauf chef "$PW2"
ok "vorhandenes Konto: Passwort neu gesetzt" '[ $CODE = 0 ] && [ "$(feld hash)" != "$HASH1" ] && echo "$AUS" | grep -q "zurückgesetzt"'
lauf chef kurz
ok "zu kurzes Passwort abgelehnt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "zu kurz"'
lauf "Groß Falsch" "$PW1"
ok "ungültiger Benutzername abgelehnt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Ungültiger Benutzername"'

# Mitarbeiter „ohne Anmeldung“: das Werkzeug darf daraus kein anmeldefähiges Konto machen (verdeckter Kontozustand)
php -r '$p=$argv[1]; $r=file_get_contents($p); $k=strpos($r, "{"); $j=json_decode(substr($r, $k), true); $j["users"][0]["zugang"]=false; file_put_contents($p, substr($r, 0, $k) . json_encode($j));' "$NUTZER"
HASH2=$(feld hash)
lauf chef "$PW1"
ok "Konto ohne Anmeldung abgelehnt, Hinweis auf die Verwaltung" '[ $CODE = 1 ] && echo "$AUS" | grep -q "keine Anmeldung" && echo "$AUS" | grep -q "Verwaltung"'
ok "Konto unverändert (Passwort und Zustand bleiben)" '[ "$(feld hash)" = "$HASH2" ] && [ "$(feld zugang)" = false ]'

echo "Passwort zurücksetzen: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
