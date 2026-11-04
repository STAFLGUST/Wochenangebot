#!/bin/sh
# Test von deploy/notzugang.sh (Notzugang über einen SSH-Tunnel, ADR-007 Regel 6) – mit Platzhalter für docker compose,
# in einem Wegwerf-Ordner.
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
ok "ohne Eintrag: geschlossen (Normalbetrieb)" '[ $CODE = 0 ] && echo "$AUS" | grep -q "geschlossen" && ! echo "$AUS" | grep -q "ssh -L"'
AUS=$(sh "$REPO/deploy/notzugang.sh" an) && CODE=0 || CODE=$?
ok "an: Eintrag gesetzt, nur app-mitarbeiter neu erstellt (nicht die Kundenseite)" '[ $CODE = 0 ] && grep -qx "WA_NOTZUGANG=an" .env && grep -qx "up -d app-mitarbeiter" aufrufe && ! grep -qx "up -d app" aufrufe'
ok "an: Weg über den SSH-Tunnel genannt (Port 8190, localhost), nie angebot-stafl.de" 'echo "$AUS" | grep -q "ssh -L 8190:127.0.0.1:8190" && echo "$AUS" | grep -q "http://localhost:8190/admin/" && ! echo "$AUS" | grep -q "angebot-stafl.de/admin" && echo "$AUS" | grep -q "notzugang.sh aus"'
ok "übrige Einträge unverändert, letzte Zeile nicht zerstört" 'grep -qx "OIDC_SECRET_ANGEBOT=geheim-bleibt" .env && grep -qx "DOMAIN=angebot-stafl.de" .env && [ "$(wc -l < .env)" = 3 ]'
ok "Rechte von .env bleiben (nur Besitzer)" '[ "$(stat -c %a .env)" = 600 ]'
AUS=$(sh "$REPO/deploy/notzugang.sh" status)
ok "status: offen, mit Weg über den Tunnel" 'echo "$AUS" | grep -q "OFFEN" && echo "$AUS" | grep -q "ssh -L 8190"'
AUS=$(sh "$REPO/deploy/notzugang.sh" an)
ok "an ein zweites Mal: unverändert, kein Neustart" 'echo "$AUS" | grep -q "unverändert" && [ "$(grep -c "up -d" aufrufe)" = 1 ]'
AUS=$(sh "$REPO/deploy/notzugang.sh" aus)
ok "aus: genau ein Eintrag, geschlossen, neu erstellt" '[ "$(grep -c "^WA_NOTZUGANG=" .env)" = 1 ] && grep -qx "WA_NOTZUGANG=aus" .env && [ "$(grep -c "up -d app-mitarbeiter" aufrufe)" = 2 ]'
AUS=$(sh "$REPO/deploy/notzugang.sh" vielleicht 2>&1) && CODE=0 || CODE=$?
ok "unbekannter Befehl abgelehnt, nichts geändert" '[ $CODE = 2 ] && grep -qx "WA_NOTZUGANG=aus" .env'
# Eigener Port (NOTZUGANG_PORT in .env)
echo "NOTZUGANG_PORT=8291" >> .env
AUS=$(sh "$REPO/deploy/notzugang.sh" an)
ok "eigener Port aus .env im Hinweis" 'echo "$AUS" | grep -q "ssh -L 8291:127.0.0.1:8291" && echo "$AUS" | grep -q "http://localhost:8291/admin/"'
sh "$REPO/deploy/notzugang.sh" aus >/dev/null
# Umstieg: frühere Zeile WA_EIGENE_ANMELDUNG (Notzugang auf der Kundenseite) wird beim Umschalten entfernt
printf 'WA_EIGENE_ANMELDUNG=an\n' >> .env
AUS=$(sh "$REPO/deploy/notzugang.sh" status)
ok "frühere Zeile WA_EIGENE_ANMELDUNG=an öffnet nichts mehr (status: geschlossen)" 'echo "$AUS" | grep -q "geschlossen"'
AUS=$(sh "$REPO/deploy/notzugang.sh" aus)
ok "aus mit früherer Zeile: Zeile entfernt (Hinweis), WA_NOTZUGANG=aus, app-mitarbeiter neu erstellt" '! grep -q "^WA_EIGENE_ANMELDUNG=" .env && grep -qx "WA_NOTZUGANG=aus" .env && echo "$AUS" | grep -q "frühere Zeile" && [ "$(grep -c "up -d app-mitarbeiter" aufrufe)" = 5 ]'
mkdir leer && cd leer
AUS=$(sh "$REPO/deploy/notzugang.sh" an 2>&1) && CODE=0 || CODE=$?
ok "ohne .env: Abbruch mit Hinweis" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Installationsordner"'
echo "notzugang.sh: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
