#!/bin/sh
# Test von deploy/notzugang.sh – mit Platzhalter für docker compose, in einem Wegwerf-Ordner.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
printf '#!/bin/sh\necho "$*" >> "%s/aufrufe"\n' "$T" > "$T/compose"; chmod +x "$T/compose"
export COMPOSE="$T/compose" AUS CODE
printf 'DOMAIN=angebot-stafl.de\nOIDC_SECRET_ANGEBOT=geheim-bleibt' > "$T/.env"; chmod 600 "$T/.env"   # ohne Zeilenende
cd "$T"
AUS=$(sh "$REPO/deploy/notzugang.sh" status) && CODE=0 || CODE=$?
ok "ohne Eintrag: geschlossen (Normalbetrieb)" '[ $CODE = 0 ] && echo "$AUS" | grep -q "geschlossen"'
AUS=$(sh "$REPO/deploy/notzugang.sh" an) && CODE=0 || CODE=$?
ok "an: Eintrag gesetzt, App neu erstellt, Hinweis zum Schließen" '[ $CODE = 0 ] && grep -qx "WA_EIGENE_ANMELDUNG=an" .env && grep -qx "up -d app" aufrufe && echo "$AUS" | grep -q "notzugang.sh aus"'
ok "übrige Einträge unverändert, letzte Zeile nicht zerstört" 'grep -qx "OIDC_SECRET_ANGEBOT=geheim-bleibt" .env && grep -qx "DOMAIN=angebot-stafl.de" .env && [ "$(wc -l < .env)" = 3 ]'
ok "Rechte von .env bleiben (nur Besitzer)" '[ "$(stat -c %a .env)" = 600 ]'
AUS=$(sh "$REPO/deploy/notzugang.sh" status)
ok "status: offen" 'echo "$AUS" | grep -q "OFFEN"'
AUS=$(sh "$REPO/deploy/notzugang.sh" an)
ok "an ein zweites Mal: unverändert, kein Neustart" 'echo "$AUS" | grep -q "unverändert" && [ "$(grep -c "up -d app" aufrufe)" = 1 ]'
AUS=$(sh "$REPO/deploy/notzugang.sh" aus)
ok "aus: genau ein Eintrag, geschlossen, neu erstellt" '[ "$(grep -c "^WA_EIGENE_ANMELDUNG=" .env)" = 1 ] && grep -qx "WA_EIGENE_ANMELDUNG=aus" .env && [ "$(grep -c "up -d app" aufrufe)" = 2 ]'
AUS=$(sh "$REPO/deploy/notzugang.sh" vielleicht 2>&1) && CODE=0 || CODE=$?
ok "unbekannter Befehl abgelehnt, nichts geändert" '[ $CODE = 2 ] && grep -qx "WA_EIGENE_ANMELDUNG=aus" .env'
mkdir leer && cd leer
AUS=$(sh "$REPO/deploy/notzugang.sh" an 2>&1) && CODE=0 || CODE=$?
ok "ohne .env: Abbruch mit Hinweis" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Installationsordner"'
echo "notzugang.sh: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
