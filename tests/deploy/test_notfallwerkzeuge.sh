#!/bin/sh
# Test der Notfallwerkzeuge (wartung-aus, ip-freigabe-aus, notfall-aus, passwort-zuruecksetzen): Sie laufen im Container, der alle
# Daten sieht – mit der Ergänzungsdatei der Anmeldung app-mitarbeiter (nach der Datentrennung, ADR-007 Stufe 2a, sieht die
# Kundenseite interne Daten wie Nutzer oder Modulstatus nicht mehr), sonst app. Platzhalter für docker, Wegwerf-Ordner.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
AUS=""
export AUS
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
printf '#!/bin/sh\necho "docker $*" >> "%s/aufrufe"\ncat > /dev/null\n' "$T" > "$T/docker"; chmod +x "$T/docker"
export DOCKER="$T/docker"
mkdir -p "$T/i/deploy"
for w in wartung-aus ip-freigabe-aus notfall-aus passwort-zuruecksetzen; do cp "$REPO/deploy/$w.sh" "$REPO/deploy/$w.php" "$T/i/deploy/"; done
for ART in ohne mit; do
  if [ "$ART" = mit ]; then printf 'DOMAIN=x\nCOMPOSE_FILE=docker-compose.yml:deploy/anmeldung/docker-compose.anmeldung.yml\n' > "$T/i/.env"; D=app-mitarbeiter
  else printf 'DOMAIN=x\n' > "$T/i/.env"; D=app; fi
  : > "$T/aufrufe"
  (cd "$T/i" && sh deploy/wartung-aus.sh && sh deploy/ip-freigabe-aus.sh && sh deploy/notfall-aus.sh --streng-behalten && sh deploy/passwort-zuruecksetzen.sh admin) >/dev/null
  AUS=$(cat "$T/aufrufe")
  export D
  ok "$ART Ergänzungsdatei: alle vier Werkzeuge im Dienst $D" '[ "$(grep -c "^docker compose exec -T -u www-data.* $D php" "$T/aufrufe")" = 4 ] && grep -q "NOTFALL_AUS=streng $D php" "$T/aufrufe" && [ "$(wc -l < "$T/aufrufe")" = 4 ]'
done
echo "Notfallwerkzeuge: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
