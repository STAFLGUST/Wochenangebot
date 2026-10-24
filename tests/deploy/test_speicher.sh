#!/bin/sh
# Test von deploy/speicher.sh – mit Platzhalter für docker, in einem Wegwerf-Ordner.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
# Platzhalter: zwei Container (App, Keycloak), Images: genutzt, Rückfall-Image, altes Keycloak, namenloses
cat > "$T/docker" <<STUB
#!/bin/sh
echo "\$*" >> "$T/aufrufe"
case "\$*" in
  "ps -aq --no-trunc"|"ps -aq") printf 'c1\nc2\n' ;;
  "inspect -f {{.Image}} c1") echo sha256:app ;;
  "inspect -f {{.Image}} c2") echo sha256:kc26 ;;
  "inspect -f {{.LogPath}} "*) echo "$T/log-\$4" ;;
  "inspect -f {{.Name}} c1") echo /wochenangebot-app-1 ;;
  "inspect -f {{.Name}} c2") echo /wochenangebot-keycloak-1 ;;
  "images --no-trunc --format {{.ID}} {{.Repository}}") printf 'sha256:app stafl-app\nsha256:vorher stafl-app\nsha256:kc26 quay.io/keycloak/keycloak\nsha256:kc25 quay.io/keycloak/keycloak\nsha256:los <none>\n' ;;
  "images --no-trunc --format {{.ID}} {{.Repository}}:{{.Tag}} {{.Size}}") printf 'sha256:app stafl-app:lokal 600MB\nsha256:vorher stafl-app:release-vorher 600MB\nsha256:kc26 quay.io/keycloak/keycloak:<none> 450MB\nsha256:kc25 quay.io/keycloak/keycloak:26.4 440MB\nsha256:los <none>:<none> 120MB\n' ;;
  "system df") echo "TYPE TOTAL ACTIVE SIZE RECLAIMABLE" ;;
  "info") [ -f "$T/ohne-docker" ] && exit 1 || true ;;
  "image rm "*|"builder prune -f"|"image prune -f") ;;
  *) echo "unerwartet: \$*" >&2; exit 9 ;;
esac
STUB
chmod +x "$T/docker"
export DOCKER="$T/docker" AUS CODE
mkdir -p "$T/i/daten/protokoll" "$T/i/sicherungen" && cd "$T/i" && touch .env docker-compose.yml daten/protokoll/2026-09 daten/protokoll/2026-10
head -c 20000 /dev/zero > "$T/log-c1"
AUS=$(sh "$REPO/deploy/speicher.sh") && CODE=0 || CODE=$?
ok "anzeigen: läuft, nennt Protokolle der Container und Monate des Aktivitätsprotokolls" '[ $CODE = 0 ] && echo "$AUS" | grep -q "wochenangebot-app-1" && echo "$AUS" | grep -q "2 Monate"'
ok "anzeigen: ungenutzt nur altes Keycloak und namenloses Image" 'echo "$AUS" | grep -q "keycloak:26.4" && echo "$AUS" | grep -q "<none>:<none>" && ! echo "$AUS" | grep -q "  [0-9]*MB  stafl-app"'
ok "anzeigen: entfernt nichts" '! grep -q "image rm\|prune" "$T/aufrufe"'
: > "$T/aufrufe"
AUS=$(sh "$REPO/deploy/speicher.sh" aufraeumen) && CODE=0 || CODE=$?
ok "aufräumen: Bauzwischenspeicher geleert" '[ $CODE = 0 ] && grep -qx "builder prune -f" "$T/aufrufe"'
ok "aufräumen: altes Keycloak über den Namen, namenloses über die Kennung entfernt" 'grep -qx "image rm quay.io/keycloak/keycloak:26.4" "$T/aufrufe" && grep -qx "image rm sha256:los" "$T/aufrufe"'
ok "aufräumen: genutzte Images und stafl-app (auch Rückfall-Image) bleiben, nie -f, nie Volumes" '! grep -q "image rm .*\(stafl-app\|sha256:app\|sha256:vorher\|sha256:kc26\)" "$T/aufrufe" && ! grep -q -- " -f [^ ]*\$\|rm -f\|volume" "$T/aufrufe"'
ok "aufräumen: Daten unverändert" '[ -f daten/protokoll/2026-09 ] && [ -f daten/protokoll/2026-10 ]'
touch "$T/ohne-docker"; : > "$T/aufrufe"
AUS=$(sh "$REPO/deploy/speicher.sh" 2>&1) && CODE=0 || CODE=$?
ok "ohne Docker: Anzeige der Daten mit Hinweis" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Docker ist nicht erreichbar" && echo "$AUS" | grep -q "daten/protokoll"'
AUS=$(sh "$REPO/deploy/speicher.sh" aufraeumen 2>&1) && CODE=0 || CODE=$?
ok "ohne Docker: Aufräumen abgelehnt, nichts entfernt" '[ $CODE = 1 ] && ! grep -q "image rm\|prune" "$T/aufrufe"'
rm "$T/ohne-docker"
AUS=$(sh "$REPO/deploy/speicher.sh" loeschen-alles 2>&1) && CODE=0 || CODE=$?
ok "unbekannter Befehl abgelehnt" '[ $CODE = 2 ]'
mkdir "$T/leer" && cd "$T/leer"
AUS=$(sh "$REPO/deploy/speicher.sh" 2>&1) && CODE=0 || CODE=$?
ok "außerhalb des Installationsordners: Abbruch mit Hinweis" '[ $CODE = 1 ] && echo "$AUS" | grep -q "/opt/wochenangebot"'
# Container-Protokolle begrenzt: jeder Dienst in jeder Compose-Datei (app, caddy · keycloak, keycloak-db · app-test)
AUS=$(grep -c 'max-size: "10m"' "$REPO/docker-compose.yml" "$REPO/deploy/anmeldung/docker-compose.anmeldung.yml" "$REPO/deploy/testumgebung/docker-compose.yml")
ok "Compose: Protokollbegrenzung für alle Dienste" 'echo "$AUS" | grep -q "docker-compose.yml:2" && echo "$AUS" | grep -q "anmeldung.yml:2" && echo "$AUS" | grep -q "testumgebung/docker-compose.yml:1"'
echo "speicher.sh: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
