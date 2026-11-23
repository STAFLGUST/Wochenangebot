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
ok "an ein zweites Mal: unverändert, Container nur abgeglichen (ohne --force-recreate)" 'echo "$AUS" | grep -q "unverändert" && [ "$(grep -c "up -d" aufrufe)" = 2 ] && ! grep -q "force-recreate" aufrufe'
AUS=$(sh "$REPO/deploy/notzugang.sh" aus)
ok "aus: genau ein Eintrag, geschlossen, neu erstellt" '[ "$(grep -c "^WA_NOTZUGANG=" .env)" = 1 ] && grep -qx "WA_NOTZUGANG=aus" .env && [ "$(grep -c "up -d app-mitarbeiter" aufrufe)" = 3 ]'
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
ok "aus mit früherer Zeile: Zeile entfernt (Hinweis), WA_NOTZUGANG=aus, app-mitarbeiter neu erstellt" '! grep -q "^WA_EIGENE_ANMELDUNG=" .env && grep -qx "WA_NOTZUGANG=aus" .env && echo "$AUS" | grep -q "frühere Zeile" && [ "$(grep -c "up -d app-mitarbeiter" aufrufe)" = 6 ]'
# compose up scheitert (Docker hängt, Abbild fehlt): Ersatz, der wie compose den Wert aus der Umgebung vor .env nimmt und sich
# den Wert des laufenden Containers merkt (exec … printenv liefert ihn)
cat > "$T/compose2" <<'EOF2'
#!/bin/sh
case "$1" in
  up) [ ! -f "$T/up-fehler" ] || { echo "Error response from daemon: Conflict"; exit 1; }
      echo "${WA_NOTZUGANG:-$(sed -n 's/^WA_NOTZUGANG=//p' .env | tail -1)}" > "$T/laufend"; echo up >> "$T/aufrufe2" ;;
  exec) cat "$T/laufend" 2>/dev/null ;;
esac
EOF2
chmod +x "$T/compose2"; export T
COMPOSE="$T/compose2" sh "$REPO/deploy/notzugang.sh" an >/dev/null
touch "$T/up-fehler"
AUS=$(COMPOSE="$T/compose2" sh "$REPO/deploy/notzugang.sh" aus 2>&1) && CODE=0 || CODE=$?
ok "aus, compose up scheitert: Fehler, .env bleibt beim laufenden Stand (an)" '[ $CODE = 1 ] && grep -qx "WA_NOTZUGANG=an" .env && [ "$(cat "$T/laufend")" = an ] && echo "$AUS" | grep -q ".env unverändert"'
AUS=$(COMPOSE="$T/compose2" sh "$REPO/deploy/notzugang.sh" status)
ok "… status meldet weiter OFFEN" 'echo "$AUS" | grep -q "OFFEN"'
rm "$T/up-fehler"
AUS=$(COMPOSE="$T/compose2" sh "$REPO/deploy/notzugang.sh" aus) && CODE=0 || CODE=$?
ok "… zweiter Aufruf wirkt: Container und .env geschlossen" '[ $CODE = 0 ] && grep -qx "WA_NOTZUGANG=aus" .env && [ "$(cat "$T/laufend")" = aus ]'
echo an > "$T/laufend"   # laufender Container offen, .env sagt aus (z. B. .env von Hand geändert)
AUS=$(COMPOSE="$T/compose2" sh "$REPO/deploy/notzugang.sh" status)
ok "status fragt den laufenden Container: offen, obwohl .env aus sagt" 'echo "$AUS" | grep -q "OFFEN" && grep -qx "WA_NOTZUGANG=aus" .env'
N2=$(wc -l < "$T/aufrufe2"); export N2
AUS=$(COMPOSE="$T/compose2" sh "$REPO/deploy/notzugang.sh" aus) && CODE=0 || CODE=$?
ok "aus bei .env schon aus: unverändert, aber Container abgeglichen und geschlossen" '[ $CODE = 0 ] && echo "$AUS" | grep -q "unverändert" && [ "$(wc -l < "$T/aufrufe2")" = $((N2 + 1)) ] && [ "$(cat "$T/laufend")" = aus ]'
AUS=$(COMPOSE="$T/compose2" sh "$REPO/deploy/notzugang.sh" status)
ok "… danach geschlossen" 'echo "$AUS" | grep -q "geschlossen"'
mkdir leer && cd leer
AUS=$(sh "$REPO/deploy/notzugang.sh" an 2>&1) && CODE=0 || CODE=$?
ok "ohne .env: Abbruch mit Hinweis" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Installationsordner"'
echo "notzugang.sh: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
