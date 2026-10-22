#!/bin/sh
# Integrationstest des Release-Modus (deploy/freigabe-einspielen.sh) – komplett lokal:
# eigenes Git-„origin“, GitHub-API-Ersatz, PHP-Testserver als Live-Seite, echte Datensicherung.
# Prüft: kein Release → nichts passiert; freigegebener Commit geht live; defekter Release wird erkannt und
# automatisch zurückgesetzt (und nicht erneut versucht); Release ohne CI und Commit außerhalb von main werden abgelehnt;
# Sicherung mit dem Skript des neuen Commits; Anwendungs-Image wird nur bei Änderungen unter deploy/image/ (und aktiver
# Ergänzungsdatei der Anmeldung) gebaut, ein Bau-Fehler verhindert das Einspielen, beim Rückfall gilt das alte Image.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d)
API_PORT=8796; WEB_PORT=8797
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; fi; }
cleanup() { kill "$API_PID" "$WEB_PID" 2>/dev/null || true; rm -rf "$T"; }
trap cleanup EXIT

# Ursprung mit Stand A
mkdir -p "$T/src"
(cd "$REPO" && git ls-files -co --exclude-standard -z | xargs -0 tar cf - --no-recursion) | tar xf - -C "$T/src"
git -C "$T/src" init -q -b main && git -C "$T/src" -c user.name=t -c user.email=t@t add -A && git -C "$T/src" -c user.name=t -c user.email=t@t commit -qm A
git clone -q --bare "$T/src" "$T/origin.git"
git clone -q "$T/origin.git" "$T/basis"
B="$T/basis"
A_SHA=$(git -C "$B" rev-parse HEAD); export A_SHA   # in den Prüfausdrücken verwendet
commit() { # name datei befehl
  git -C "$T/src" pull -q "$T/origin.git" main
  sh -c "$3"
  git -C "$T/src" -c user.name=t -c user.email=t@t commit -qam "$1"
  git -C "$T/src" push -q "$T/origin.git" main
  git -C "$T/src" rev-parse HEAD
}
G_SHA=$(commit gut x "echo '<!-- gut -->' >> '$T/src/app/index.html'")
X_SHA=$(commit kaputt x "sed -i 's/^declare(strict_types=1);/declare(strict_types=1); kaputt(/' '$T/src/app/api/index.php'")
# Commit nur auf einem Nebenzweig
git -C "$T/src" checkout -q -b neben
echo '<!-- neben -->' >> "$T/src/app/index.html"; git -C "$T/src" -c user.name=t -c user.email=t@t commit -qam neben
git -C "$T/src" push -q "$T/origin.git" neben; N_SHA=$(git -C "$T/src" rev-parse HEAD); git -C "$T/src" checkout -q main

# Testdaten, Umgebung, Server
cp -r "$REPO/tests/fixtures/data-seed/." "$B/app/data/"
ln -s "$B/app/data" "$B/daten"
printf 'GITHUB_REPO=x/y\nGITHUB_TOKEN_LESEN=test-token\nDOMAIN=test.local\n' > "$B/.env"
echo '{}' > "$T/state.json"
# Docker-Ersatz: gibt Befehle aus; „build“ schlägt fehl, solange $T/bau-fehler existiert
cat > "$T/compose.sh" <<STUB
#!/bin/sh
echo "compose \$*\${STAFL_APP_VERSION:+ [STAFL_APP_VERSION=\$STAFL_APP_VERSION]}"
# beim Bau: aktiver Commit, ob app/ unverändert ist, und letzte Zeile des Bauplans
[ "\$1" = build ] && echo "bau-stand \$(git rev-parse HEAD) app-\$(git diff --quiet HEAD -- app && echo alt || echo neu) \$(tail -1 deploy/image/Dockerfile)"
if [ "\$1" = build ] && [ -f "$T/bau-fehler" ]; then echo "Bau fehlgeschlagen"; exit 1; fi
exit 0
STUB
python3 "$REPO/tests/deploy/github_stub.py" $API_PORT "$T/state.json" & API_PID=$!
(cd "$B/app" && exec php -S 127.0.0.1:$WEB_PORT >/dev/null 2>&1) & WEB_PID=$!
sleep 1
lauf() { WA_BASIS="$B" WA_API="http://127.0.0.1:$API_PORT" WA_HEALTH_URL="http://127.0.0.1:$WEB_PORT" WA_HEALTH_HOST="test.local:80:127.0.0.1" \
         WA_COMPOSE="sh $T/compose.sh" WA_DOCKER="echo docker" sh "$B/deploy/freigabe-einspielen.sh" > "$T/out.txt" 2>&1; rc=$?; [ -z "${DEBUG:-}" ] || { echo "--- rc=$rc"; cat "$T/out.txt"; }; return $rc; }
kopf() { git -C "$B" rev-parse HEAD; }
st() { python3 -c "import json,sys; t=open('$B/daten/deployment.php').read(); print(json.loads(t[t.index(chr(10))+1:]).get('$1'))"; }

lauf; ok "kein Release: nichts passiert" '[ "$(kopf)" = "$A_SHA" ]'

printf '{"release":"%s","ci_ok":["%s"]}' "$G_SHA" "$G_SHA" > "$T/state.json"
lauf; ok "freigegebener Commit geht live" '[ "$(kopf)" = "$G_SHA" ] && [ "$(st ok)" = True ]'
ok "vor dem Release gesichert" '[ -n "$(ls "$B"/sicherungen/daten-*.tar.gz 2>/dev/null)" ]'
lauf; ok "erneuter Lauf: keine Änderung" '[ "$(kopf)" = "$G_SHA" ]'


printf '{"release":"%s","ci_ok":["%s","%s"]}' "$X_SHA" "$G_SHA" "$X_SHA" > "$T/state.json"
lauf || true
ok "defekter Release: automatisch zurück auf Vorversion" '[ "$(kopf)" = "$G_SHA" ] && [ "$(st ok)" = False ] && grep -q "zurückgesetzt" "$B/daten/deployment.php"'
ok "Seite nach Rückfall erreichbar" 'curl -fsS "http://127.0.0.1:$WEB_PORT/api/?action=status" | grep -q "\"ok\":true"'
lauf || true; ok "defekter Release wird nicht erneut versucht" '[ "$(kopf)" = "$G_SHA" ] && [ "$(cat "$B/.release-abgelehnt")" = "$X_SHA" ]'

rm -f "$B/.release-abgelehnt"
printf '{"release":"%s","ci_ok":["%s"]}' "$X_SHA" "$G_SHA" > "$T/state.json"
lauf || true; ok "Release ohne erfolgreiche CI abgelehnt" '[ "$(kopf)" = "$G_SHA" ] && grep -q "ohne erfolgreiche CI" "$T/out.txt"'

printf '{"release":"%s","ci_ok":["%s"]}' "$N_SHA" "$N_SHA" > "$T/state.json"
lauf || true; ok "Commit außerhalb von main abgelehnt" '[ "$(kopf)" = "$G_SHA" ] && grep -q "nicht auf main" "$T/out.txt"'

printf '{"release":"%s","release_branch":"neben","ci_ok":["%s"]}' "$N_SHA" "$N_SHA" > "$T/state.json"
lauf || true; ok "Release-Lauf von einem Nebenzweig ignoriert" '[ "$(kopf)" = "$G_SHA" ]'

# Wochenangebot nur für angemeldete Kunden (Angebots-API antwortet 401) – Release muss trotzdem durchgehen
H_SHA=$(commit repariert x "sed -i 's/ kaputt(//' '$T/src/app/api/index.php'")
printf '%s\n{"rev":1,"offers":[],"stdPublic":false}' '<?php http_response_code(404); exit; ?>' > "$B/daten/angebote.php"
ok "Testvoraussetzung: Angebot verlangt Anmeldung" '[ "$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$WEB_PORT/api/?action=offer")" = 401 ]'
printf '{"release":"%s","ci_ok":["%s"]}' "$H_SHA" "$H_SHA" > "$T/state.json"
lauf || true; ok "nicht öffentliches Wochenangebot: Release geht live" '[ "$(kopf)" = "$H_SHA" ] && [ "$(st ok)" = True ]'
rm -f "$B/daten/angebote.php"

# Wartungsmodus eingeschaltet (Angebots-API antwortet 503 mit wartung:true) – Release muss trotzdem durchgehen
W_SHA=$(commit gut3 x "echo '<!-- gut3 -->' >> '$T/src/app/index.html'")
printf '%s\n{"active":true,"message":"Test"}' '<?php http_response_code(404); exit; ?>' > "$B/daten/wartung.php"
ok "Testvoraussetzung: Wartungsmodus aktiv" '[ "$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$WEB_PORT/api/?action=offer")" = 503 ]'
printf '{"release":"%s","ci_ok":["%s"]}' "$W_SHA" "$W_SHA" > "$T/state.json"
lauf || true; ok "Wartungsmodus: Release geht live" '[ "$(kopf)" = "$W_SHA" ] && [ "$(st ok)" = True ]'
ok "nur Code geändert: Container werden nicht neu erstellt" '! grep -qE "^(compose|docker)" "$T/out.txt"'
rm -f "$B/daten/wartung.php"
# Ergänzungsdatei der Anmeldung geändert (COMPOSE_FILE in .env): Container neu erstellen wie bei docker-compose.yml
C_SHA=$(commit ergaenzung x "echo '# geändert' >> '$T/src/deploy/anmeldung/docker-compose.anmeldung.yml'")
printf '{"release":"%s","ci_ok":["%s"]}' "$C_SHA" "$C_SHA" > "$T/state.json"
lauf || true; ok "Ergänzungsdatei der Anmeldung geändert: Container werden neu erstellt" '[ "$(kopf)" = "$C_SHA" ] && grep -q "^compose up -d --force-recreate" "$T/out.txt"'

# Sicherung vor dem Release mit dem Skript des NEUEN Commits (ein defektes altes Skript blockiert die Korrektur nicht)
ok "temporäres Sicherungsskript steht in .gitignore" 'git -C "$REPO" check-ignore -q deploy/.sichern-release.sh'
K_SHA=$(commit sichern-kaputt x "sed -i 's/^set -eu\$/set -eu; echo kaputt; exit 3/' '$T/src/deploy/sichern.sh'")
printf '{"release":"%s","ci_ok":["%s"]}' "$K_SHA" "$K_SHA" > "$T/state.json"
lauf || true
ok "neues Sicherungsskript defekt: nicht eingespielt" '[ "$(kopf)" = "$C_SHA" ] && [ "$(st ok)" = False ] && grep -q "Sicherung vor dem Release fehlgeschlagen" "$B/daten/deployment.php" && [ ! -e "$B/deploy/.sichern-release.sh" ]'
git -C "$B" reset -q --hard "$K_SHA"   # Lage wie im Betrieb: aktiver Stand mit defektem Sicherungsskript
ok "Testvoraussetzung: aktives Sicherungsskript defekt" '! sh "$B/deploy/sichern.sh" --jetzt >/dev/null 2>&1'
F_SHA=$(commit sichern-repariert x "sed -i 's/^set -eu; echo kaputt; exit 3\$/set -eu/' '$T/src/deploy/sichern.sh'")
anzahl() { find "$B/sicherungen" -maxdepth 1 -name 'daten-*.tar.gz' | wc -l; }
N0=0; export N0   # in den Prüfausdrücken verwendet
N0=$(anzahl)
printf '{"release":"%s","ci_ok":["%s"]}' "$F_SHA" "$F_SHA" > "$T/state.json"
lauf || true
ok "altes Sicherungsskript defekt, neues funktioniert: Release geht live" '[ "$(kopf)" = "$F_SHA" ] && [ "$(st ok)" = True ] && [ "$(anzahl)" -gt "$N0" ]'
ok "temporäres Sicherungsskript danach entfernt" '[ ! -e "$B/deploy/.sichern-release.sh" ]'
M_SHA=$(commit ohne-sichern x "git -C '$T/src' rm -q deploy/sichern.sh")
N0=$(anzahl)
printf '{"release":"%s","ci_ok":["%s"]}' "$M_SHA" "$M_SHA" > "$T/state.json"
lauf || true
ok "neuer Commit ohne Sicherungsskript: vorhandenes Skript sichert" '[ "$(kopf)" = "$M_SHA" ] && [ "$(st ok)" = True ] && [ "$(anzahl)" -gt "$N0" ]'
R_SHA=$(commit sichern-zurueck x "git -C '$T/src' checkout HEAD~1 -- deploy/sichern.sh")
N0=$(anzahl)
printf '{"release":"%s","ci_ok":["%s"]}' "$R_SHA" "$R_SHA" > "$T/state.json"
lauf || true
ok "aktiver Stand ohne Sicherungsskript: Skript des neuen Commits sichert" '[ "$(kopf)" = "$R_SHA" ] && [ "$(st ok)" = True ] && [ "$(anzahl)" -gt "$N0" ]'

# Anwendungs-Image (deploy/image): nur mit aktiver Ergänzungsdatei (COMPOSE_FILE in .env) bauen
I0_SHA=$(commit image-ohne-anmeldung x "echo '# Update 1' >> '$T/src/deploy/image/Dockerfile'")
printf '{"release":"%s","ci_ok":["%s"]}' "$I0_SHA" "$I0_SHA" > "$T/state.json"
lauf || true
ok "Image geändert ohne COMPOSE_FILE: kein Bau, keine neuen Container" '[ "$(kopf)" = "$I0_SHA" ] && [ "$(st ok)" = True ] && ! grep -qE "^(compose|docker)" "$T/out.txt"'
cp "$B/.env" "$T/env.ohne"
printf 'COMPOSE_FILE=docker-compose.yml:deploy/anmeldung/docker-compose.anmeldung.yml\n' >> "$B/.env"
I_SHA=$(commit image x "echo '# Update 2' >> '$T/src/deploy/image/Dockerfile'")
printf '{"release":"%s","ci_ok":["%s"]}' "$I_SHA" "$I_SHA" > "$T/state.json"
lauf || true
ok "Image geändert mit COMPOSE_FILE: gebaut, umgetaggt, Container neu erstellt" '[ "$(kopf)" = "$I_SHA" ] && [ "$(st ok)" = True ] \
  && grep -q "^compose build --pull app \[STAFL_APP_VERSION=release-neu\]" "$T/out.txt" \
  && grep -q "^docker tag stafl-app:lokal stafl-app:release-vorher" "$T/out.txt" && grep -q "^docker tag stafl-app:release-neu stafl-app:lokal" "$T/out.txt" \
  && grep -qx "compose up -d --force-recreate app" "$T/out.txt"'
ok "Image mit dem neuen Bauplan gebaut, bevor der Code wechselt" 'grep -q "^bau-stand $I0_SHA app-alt # Update 2" "$T/out.txt"'
J_SHA=$(commit nur-code x "echo '<!-- j -->' >> '$T/src/app/index.html'")
printf '{"release":"%s","ci_ok":["%s"]}' "$J_SHA" "$J_SHA" > "$T/state.json"
lauf || true
ok "nur Code geändert mit COMPOSE_FILE: kein Bau, keine neuen Container" '[ "$(kopf)" = "$J_SHA" ] && [ "$(st ok)" = True ] && ! grep -qE "^(compose|docker)" "$T/out.txt"'
touch "$T/bau-fehler"
P_SHA=$(commit image-baufehler x "echo '# Update 3' >> '$T/src/deploy/image/Dockerfile'")
N0=$(anzahl)
printf '{"release":"%s","ci_ok":["%s"]}' "$P_SHA" "$P_SHA" > "$T/state.json"
lauf || true
ok "Image-Bau fehlgeschlagen: nicht eingespielt, Status ok:false" '[ "$(kopf)" = "$J_SHA" ] && [ "$(st ok)" = False ] && grep -q "nicht gebaut werden" "$B/daten/deployment.php" \
  && ! grep -qE "^(compose up|docker tag)" "$T/out.txt" && git -C "$B" diff --quiet HEAD -- deploy docker-compose.yml && [ "$(anzahl)" = "$N0" ]'
ok "Image-Bau fehlgeschlagen: nicht dauerhaft abgelehnt" '[ "$(cat "$B/.release-abgelehnt" 2>/dev/null)" != "$P_SHA" ]'
rm -f "$T/bau-fehler"
lauf || true
ok "nach Bau-Fehler: nächster Lauf spielt ein" '[ "$(kopf)" = "$P_SHA" ] && [ "$(st ok)" = True ] && grep -q "^docker tag stafl-app:release-neu stafl-app:lokal" "$T/out.txt"'
Q_SHA=$(commit image-defekt x "echo '# Update 4' >> '$T/src/deploy/image/Dockerfile'; sed -i 's/^declare(strict_types=1);/declare(strict_types=1); kaputt(/' '$T/src/app/api/index.php'")
printf '{"release":"%s","ci_ok":["%s"]}' "$Q_SHA" "$Q_SHA" > "$T/state.json"
lauf || true
ok "Image geändert, Release defekt: zurück, altes Image wieder aktiv" '[ "$(kopf)" = "$P_SHA" ] && [ "$(st ok)" = False ] && grep -q "zurückgesetzt" "$B/daten/deployment.php" \
  && grep -q "^docker tag stafl-app:release-vorher stafl-app:lokal" "$T/out.txt" && [ "$(grep -cx "compose up -d --force-recreate app" "$T/out.txt")" = 2 ]'
S_SHA=$(commit repariert2 x "sed -i 's/ kaputt(//' '$T/src/app/api/index.php'")
printf '{"release":"%s","ci_ok":["%s"]}' "$S_SHA" "$S_SHA" > "$T/state.json"
lauf || true
ok "reparierter Release mit Image geht live" '[ "$(kopf)" = "$S_SHA" ] && [ "$(st ok)" = True ]'
E_SHA=$(commit image-und-ergaenzung x "echo '# Update 5' >> '$T/src/deploy/image/Dockerfile'; echo '# geändert 2' >> '$T/src/deploy/anmeldung/docker-compose.anmeldung.yml'")
printf '{"release":"%s","ci_ok":["%s"]}' "$E_SHA" "$E_SHA" > "$T/state.json"
lauf || true
ok "Image und Ergänzungsdatei geändert: gebaut, alle Container neu erstellt" '[ "$(kopf)" = "$E_SHA" ] && [ "$(st ok)" = True ] \
  && grep -q "^compose build --pull app" "$T/out.txt" && grep -qx "compose up -d --force-recreate" "$T/out.txt" && ! grep -qx "compose up -d --force-recreate app" "$T/out.txt"'
cp "$T/env.ohne" "$B/.env"
H_SHA=$E_SHA   # aktueller Stand für die folgenden Prüfungen

# Active SQLite must never be silently opened by an old file-only release.
L_SHA=$(commit ohne-sqlite x "rm '$T/src/app/api/storage.php'")
kill "$WEB_PID"; wait "$WEB_PID" 2>/dev/null || true
python3 "$B/deploy/datenbank.py" migrate "$B/daten" --offline >/dev/null
(cd "$B/app" && exec php -S 127.0.0.1:$WEB_PORT >/dev/null 2>&1) & WEB_PID=$!
printf '{"release":"%s","ci_ok":["%s"]}' "$L_SHA" "$L_SHA" > "$T/state.json"
lauf || true
ok "SQLite: inkompatiblen Release vor Codewechsel abweisen" '[ "$(kopf)" = "$H_SHA" ] && grep -q "SQLite aktiv" "$T/out.txt"'
printf '%s\n{"vorher":"%s"}' '<?php http_response_code(404); exit; ?>' "$L_SHA" > "$B/daten/deployment.php"
sh "$B/deploy/release-zurueck.sh" > "$T/out.txt" 2>&1 || true
ok "SQLite: auch manueller Code-Rückfall ist gesperrt" '[ "$(kopf)" = "$H_SHA" ] && grep -q "SQLite aktiv" "$T/out.txt"'

echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" -eq 0 ]
