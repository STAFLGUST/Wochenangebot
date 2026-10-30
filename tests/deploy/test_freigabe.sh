#!/bin/sh
# Integrationstest des Release-Modus (deploy/freigabe-einspielen.sh) – komplett lokal:
# eigenes Git-„origin“, GitHub-API-Ersatz, PHP-Testserver als Live-Seite, echte Datensicherung.
# Prüft: kein Release → nichts passiert; freigegebener Commit geht live; defekter Release wird erkannt und
# automatisch zurückgesetzt (und nicht erneut versucht); Release ohne CI und Commit außerhalb von main werden abgelehnt;
# Sicherung mit dem Skript des neuen Commits; Anwendungs-Image wird nur bei Änderungen unter deploy/image/ (und aktiver
# Ergänzungsdatei der Anmeldung) gebaut, ein Bau-Fehler verhindert das Einspielen, beim Rückfall gilt das alte Image;
# nach erfolgreichem Release nur hängende Images aufgeräumt (Fehler dabei unschädlich); manueller Notfall-Rückfall
# (deploy/release-zurueck.sh) mit Container-Neustart bei geänderter Konfiguration, gemerktem bzw. neu gebautem Image;
# Bereitstellung (deploy/bereitstellen.py): Versionsnummern und Prüfliste aus genau dem eingespielten Commit, auch nach
# Rückfall, neue Adresse bei geänderter Datei, fehlende Liste/Nummern nachgeholt, Übergang von und zu Ständen mit Liste.
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
# beim Bau: aktiver Commit, ob app/ unverändert ist (wie im Commit oder wie bereitgestellt), und letzte Zeile des Bauplans
[ "\$1" = build ] && echo "bau-stand \$(git rev-parse HEAD) app-\$({ git diff --quiet HEAD -- app || python3 deploy/bereitstellen.py --pruefen >/dev/null; } && echo alt || echo neu) \$(tail -1 deploy/image/Dockerfile)"
if [ "\$1" = build ] && [ -f "$T/bau-fehler" ]; then echo "Bau fehlgeschlagen"; exit 1; fi
exit 0
STUB
# Docker-Ersatz: gibt Befehle aus; stafl-app:release-vorher fehlt (inspect und tag scheitern), solange $T/kein-vorher
# existiert, „tag“ allgemein, solange $T/tag-fehler existiert, „image prune“, solange $T/prune-fehler existiert
cat > "$T/docker.sh" <<STUB
#!/bin/sh
echo "docker \$*"
if [ -f "$T/kein-vorher" ] && { [ "\$1 \$2" = "tag stafl-app:release-vorher" ] || [ "\$1 \$2 \$3" = "image inspect stafl-app:release-vorher" ]; }; then echo "Error: No such image"; exit 1; fi
if [ "\$1" = tag ] && [ -f "$T/tag-fehler" ]; then echo "Error: tag fehlgeschlagen"; exit 1; fi
if [ "\$1 \$2" = "image prune" ] && [ -f "$T/prune-fehler" ]; then echo "Cannot connect to the Docker daemon"; exit 1; fi
exit 0
STUB
python3 "$REPO/tests/deploy/github_stub.py" $API_PORT "$T/state.json" & API_PID=$!
(cd "$B/app" && exec php -S 127.0.0.1:$WEB_PORT >/dev/null 2>&1) & WEB_PID=$!
sleep 1
lauf() { WA_BASIS="$B" WA_API="http://127.0.0.1:$API_PORT" WA_HEALTH_URL="http://127.0.0.1:$WEB_PORT" WA_HEALTH_HOST="test.local:80:127.0.0.1" \
         WA_COMPOSE="sh $T/compose.sh" WA_DOCKER="sh $T/docker.sh" sh "$B/deploy/freigabe-einspielen.sh" > "$T/out.txt" 2>&1; rc=$?; [ -z "${DEBUG:-}" ] || { echo "--- rc=$rc"; cat "$T/out.txt"; }; return $rc; }
# manueller Notfall-Rückfall mit denselben Ersatzbefehlen
zurueck() { WA_COMPOSE="sh $T/compose.sh" WA_DOCKER="sh $T/docker.sh" sh "$B/deploy/release-zurueck.sh" > "$T/out.txt" 2>&1; rc=$?; [ -z "${DEBUG:-}" ] || { echo "--- rc=$rc"; cat "$T/out.txt"; }; return $rc; }
kopf() { git -C "$B" rev-parse HEAD; }
st() { python3 -c "import json,sys; t=open('$B/daten/deployment.php').read(); print(json.loads(t[t.index(chr(10))+1:]).get('$1'))"; }

lauf; ok "kein Release: nichts passiert" '[ "$(kopf)" = "$A_SHA" ]'

printf '{"release":"%s","ci_ok":["%s"]}' "$G_SHA" "$G_SHA" > "$T/state.json"
lauf; ok "freigegebener Commit geht live" '[ "$(kopf)" = "$G_SHA" ] && [ "$(st ok)" = True ]'
ok "vorheriger Stand für den Notfall-Rückfall in .release-vorher (root, außerhalb von daten/)" '[ "$(cat "$B/.release-vorher")" = "$A_SHA" ] && [ "$(st vorher)" = "$A_SHA" ] && [ -z "$(ls -A "$B" | grep "^\.status\.")" ]'
ok "nach erfolgreichem Release: nur hängende Images aufgeräumt" 'grep -qx "docker image prune -f" "$T/out.txt" && ! grep -qE "^docker (system|volume|container)|prune .*(-a|--all|--volumes|--filter)" "$T/out.txt"'
ok "vor dem Release gesichert" '[ -n "$(ls "$B"/sicherungen/daten-*.tar.gz 2>/dev/null)" ]'
lauf; ok "erneuter Lauf: keine Änderung" '[ "$(kopf)" = "$G_SHA" ]'
# Bereitstellung: Versionsnummern und Prüfliste aus genau dem eingespielten Commit
LISTE="$B/app/api/lib/integritaet-liste.php"
vnr() { python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest()[:10])" "$B/app/assets/$1"; }
seite() { curl -fsS "http://127.0.0.1:$WEB_PORT/$1"; }
ok "Release: Seiten mit Versionsnummer = Prüfsumme der ausgelieferten Datei (wie früher im Repository)" 'seite "" | grep -q "assets/frontend.js?v=$(vnr frontend.js)\"" \
  && seite admin/ | grep -q "assets/admin.js?v=$(vnr admin.js)\"" && ! git -C "$B" show HEAD:app/index.html | grep -q "?v="'
vnrp() { python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest()[:10])" "$B/$1"; }
ok "Release: auch Modulseiten (eigene Skripte relativ zur Seite) und Dashboard (neben app/, nicht in der Prüfliste)" \
  'seite module/qs/ | grep -q "src=\"qs.js?v=$(vnrp app/module/qs/qs.js)\"" && seite module/qs/ | grep -q "href=\"qs.css?v=$(vnrp app/module/qs/qs.css)\"" \
   && seite module/qs/ | grep -q "href=\"../../assets/app.css?v=$(vnr app.css)\"" \
   && grep -q "src=\"dashboard.js?v=$(vnrp dashboard/dashboard.js)\"" "$B/dashboard/index.html" \
   && grep -q "href=\"../assets/app.css?v=$(vnr app.css)\"" "$B/dashboard/index.html" \
   && ! git -C "$B" show HEAD:dashboard/index.html | grep -q "?v=" && ! grep -q "dashboard/" "$LISTE"'
ok "Release: Prüfliste aus genau diesem Commit, nicht im Repository" 'grep -q "aus Commit $G_SHA" "$LISTE" && head -1 "$LISTE" | grep -q "http_response_code(404)" \
  && [ -z "$(git -C "$B" status --porcelain -- app/api/lib)" ] && python3 "$B/deploy/bereitstellen.py" --pruefen >/dev/null'


printf '{"release":"%s","ci_ok":["%s","%s"]}' "$X_SHA" "$G_SHA" "$X_SHA" > "$T/state.json"
lauf || true
ok "defekter Release: automatisch zurück auf Vorversion" '[ "$(kopf)" = "$G_SHA" ] && [ "$(st ok)" = False ] && grep -q "zurückgesetzt" "$B/daten/deployment.php"'
ok "defekter Release: nichts aufgeräumt" '! grep -q "image prune" "$T/out.txt"'
ok "Seite nach Rückfall erreichbar" 'curl -fsS "http://127.0.0.1:$WEB_PORT/api/?action=status" | grep -q "\"ok\":true"'
ok "Rückfall: Prüfliste und Versionsnummern wieder für die Vorversion" 'grep -q "aus Commit $G_SHA" "$LISTE" && python3 "$B/deploy/bereitstellen.py" --pruefen >/dev/null \
  && seite "" | grep -q "assets/frontend.js?v=$(vnr frontend.js)\""'
lauf || true; ok "defekter Release wird nicht erneut versucht" '[ "$(kopf)" = "$G_SHA" ] && [ "$(cat "$B/.release-abgelehnt")" = "$X_SHA" ]'
# Status nach dem automatischen Rückfall nennt den abgelehnten Release als „vorher“ – der Notfall-Rückfall darf nie dorthin
zurueck || true
ok "Notfall-Rückfall nach automatischem Rückfall: nie auf den abgelehnten Release" '[ "$(kopf)" = "$G_SHA" ] && grep -q "automatisch zurückgenommen" "$T/out.txt" && [ "$(cat "$B/.release-abgelehnt")" = "$X_SHA" ]'
git -C "$B" reset -q --hard "$G_SHA"   # Ausgangslage der folgenden Prüfungen unabhängig vom Ergebnis oben

rm -f "$B/.release-abgelehnt"
# daten/ ist im Container beschreibbar: dort angelegte Verweise dürfen den Status (root) nie auf andere Dateien umlenken
echo ORIGINAL > "$T/opfer"; chmod 600 "$T/opfer"; rm -f "$B/daten/deployment.php"
ln -s "$T/opfer" "$B/daten/deployment.php"; ln -s "$T/opfer2" "$B/daten/deployment.php.tmp"
printf '{"release":"%s","ci_ok":["%s"]}' "$X_SHA" "$G_SHA" > "$T/state.json"
lauf || true; ok "Release ohne erfolgreiche CI abgelehnt" '[ "$(kopf)" = "$G_SHA" ] && grep -q "ohne erfolgreiche CI" "$T/out.txt"'
ok "Status folgt keinem Verweis in daten/ (Ziel unverändert, Verweis ersetzt)" '[ "$(cat "$T/opfer")" = ORIGINAL ] && [ "$(stat -c %a "$T/opfer")" = 600 ] && [ ! -e "$T/opfer2" ] \
  && [ ! -L "$B/daten/deployment.php" ] && grep -q "ohne erfolgreiche CI" "$B/daten/deployment.php"'
rm -f "$B/daten/deployment.php.tmp"

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
ok "nur Code geändert: Container werden nicht neu erstellt" '! grep -qE "^(compose|docker tag)" "$T/out.txt"'
rm -f "$B/daten/wartung.php"
# Aufräumen scheitert (z. B. Docker kurz nicht erreichbar): Release bleibt erfolgreich
touch "$T/prune-fehler"
RC=0; export RC   # in den Prüfausdrücken verwendet
U_SHA=$(commit gut4 x "echo '<!-- gut4 -->' >> '$T/src/app/index.html'")
printf '{"release":"%s","ci_ok":["%s"]}' "$U_SHA" "$U_SHA" > "$T/state.json"
RC=0; lauf || RC=$?
ok "Aufräumen fehlgeschlagen: Release bleibt erfolgreich" '[ "$RC" = 0 ] && [ "$(kopf)" = "$U_SHA" ] && [ "$(st ok)" = True ] \
  && grep -q "Aufräumen alter Images fehlgeschlagen" "$T/out.txt" && [ "$(cat "$B/.release-abgelehnt" 2>/dev/null)" != "$U_SHA" ]'
rm -f "$T/prune-fehler"
# Ergänzungsdatei der Anmeldung geändert (COMPOSE_FILE in .env): Container neu erstellen wie bei docker-compose.yml
C_SHA=$(commit ergaenzung x "echo '# geändert' >> '$T/src/deploy/anmeldung/docker-compose.anmeldung.yml'")
printf '{"release":"%s","ci_ok":["%s"]}' "$C_SHA" "$C_SHA" > "$T/state.json"
lauf || true; ok "Ergänzungsdatei der Anmeldung geändert: Container werden neu erstellt" '[ "$(kopf)" = "$C_SHA" ] && grep -q "^compose up -d --force-recreate" "$T/out.txt"'
# Apache-Konfiguration der Anmeldung geändert (einzeln eingebundene Datei): nur die App neu erstellen, sonst sähe sie die alte Fassung
O_SHA=$(commit apache-oidc x "echo '# geändert' >> '$T/src/deploy/anmeldung/apache-oidc.conf'")
printf '{"release":"%s","ci_ok":["%s"]}' "$O_SHA" "$O_SHA" > "$T/state.json"
lauf || true; ok "Apache-Konfiguration der Anmeldung geändert: nur die App neu erstellt" '[ "$(kopf)" = "$O_SHA" ] && grep -qx "compose up -d --force-recreate app" "$T/out.txt" && ! grep -qx "compose up -d --force-recreate" "$T/out.txt"'

# Sicherung vor dem Release mit dem Skript des NEUEN Commits (ein defektes altes Skript blockiert die Korrektur nicht)
ok "temporäres Sicherungsskript steht in .gitignore" 'git -C "$REPO" check-ignore -q deploy/.sichern-release.sh'
K_SHA=$(commit sichern-kaputt x "sed -i 's/^set -eu\$/set -eu; echo kaputt; exit 3/' '$T/src/deploy/sichern.sh'")
printf '{"release":"%s","ci_ok":["%s"]}' "$K_SHA" "$K_SHA" > "$T/state.json"
lauf || true
ok "neues Sicherungsskript defekt: nicht eingespielt" '[ "$(kopf)" = "$O_SHA" ] && [ "$(st ok)" = False ] && grep -q "Sicherung vor dem Release fehlgeschlagen" "$B/daten/deployment.php" && [ ! -e "$B/deploy/.sichern-release.sh" ]'
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
ok "Image geändert ohne COMPOSE_FILE: kein Bau, keine neuen Container" '[ "$(kopf)" = "$I0_SHA" ] && [ "$(st ok)" = True ] && ! grep -qE "^(compose|docker tag)" "$T/out.txt"'
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
ok "nur Code geändert mit COMPOSE_FILE: kein Bau, keine neuen Container" '[ "$(kopf)" = "$J_SHA" ] && [ "$(st ok)" = True ] && ! grep -qE "^(compose|docker tag)" "$T/out.txt"'
touch "$T/bau-fehler"
P_SHA=$(commit image-baufehler x "echo '# Update 3' >> '$T/src/deploy/image/Dockerfile'")
N0=$(anzahl)
printf '{"release":"%s","ci_ok":["%s"]}' "$P_SHA" "$P_SHA" > "$T/state.json"
lauf || true
ok "Image-Bau fehlgeschlagen: nicht eingespielt, Status ok:false" '[ "$(kopf)" = "$J_SHA" ] && [ "$(st ok)" = False ] && grep -q "nicht gebaut werden" "$B/daten/deployment.php" \
  && ! grep -qE "^(compose up|docker)" "$T/out.txt" && git -C "$B" diff --quiet HEAD -- deploy docker-compose.yml && [ "$(anzahl)" = "$N0" ]'
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

# Manueller Notfall-Rückfall (deploy/release-zurueck.sh): Container und Image wie beim automatischen Rückfall
zurueck_lage() { # aktiv vorher: Lage wie nach einem erfolgreichen Release von <vorher> auf <aktiv>
  git -C "$B" reset -q --hard "$1"
  printf '%s\n{"ok":true,"sha":"%s","vorher":"%s"}' '<?php http_response_code(404); exit; ?>' "$1" "$2" > "$B/daten/deployment.php"
  printf '%s\n' "$2" > "$B/.release-vorher"
  rm -f "$B/.release-abgelehnt"
}
ZC_SHA=$(commit rueck-ergaenzung x "echo '# rueck' >> '$T/src/deploy/anmeldung/docker-compose.anmeldung.yml'")
ZI_SHA=$(commit rueck-image x "echo '# Rueck 1' >> '$T/src/deploy/image/Dockerfile'")
git -C "$B" fetch -q origin main
zurueck_lage "$ZC_SHA" "$E_SHA"; zurueck || true
ok "Notfall-Rückfall, Ergänzungsdatei unterscheidet sich: alle Container neu erstellt" '[ "$(kopf)" = "$E_SHA" ] && grep -qx "compose up -d --force-recreate" "$T/out.txt" \
  && ! grep -qE "^(docker|compose build)" "$T/out.txt" && [ "$(cat "$B/.release-abgelehnt")" = "$ZC_SHA" ]'
zurueck || true; ok "Notfall-Rückfall erneut: nichts mehr zu tun" '[ "$(kopf)" = "$E_SHA" ] && grep -q "bereits aktiv" "$T/out.txt"'
# Ziel des Notfall-Rückfalls nur aus .release-vorher – daten/deployment.php kann der Container ändern
zurueck_lage "$ZC_SHA" "$E_SHA"; printf '%s\n{"vorher":"%s"}' '<?php http_response_code(404); exit; ?>' "$X_SHA" > "$B/daten/deployment.php"; zurueck || true
ok "Notfall-Rückfall: Ziel aus .release-vorher, verändertes daten/deployment.php ohne Wirkung" '[ "$(kopf)" = "$E_SHA" ]'
zurueck_lage "$ZC_SHA" "$E_SHA"; rm -f "$B/.release-vorher"; printf '%s\n{"vorher":"%s"}' '<?php http_response_code(404); exit; ?>' "$N_SHA" > "$B/daten/deployment.php"; RC=0; zurueck || RC=$?
ok "Übergang ohne .release-vorher: Stand aus daten/deployment.php nur, wenn Vorgänger des aktiven Stands" '[ "$RC" != 0 ] && [ "$(kopf)" = "$ZC_SHA" ] && grep -q "kein Vorgänger" "$T/out.txt"'
zurueck_lage "$ZC_SHA" "$E_SHA"; rm -f "$B/.release-vorher"; zurueck || true
ok "Übergang ohne .release-vorher: Vorgänger aus daten/deployment.php mit Hinweis" '[ "$(kopf)" = "$E_SHA" ] && grep -q ".release-vorher fehlt" "$T/out.txt"'
zurueck_lage "$ZI_SHA" "$ZC_SHA"; zurueck || true
ok "Notfall-Rückfall, Image unterscheidet sich: gemerktes Image wieder aktiv, nur die App neu erstellt" '[ "$(kopf)" = "$ZC_SHA" ] \
  && grep -qx "docker tag stafl-app:release-vorher stafl-app:lokal" "$T/out.txt" && grep -qx "compose up -d --force-recreate app" "$T/out.txt" \
  && ! grep -qx "compose up -d --force-recreate" "$T/out.txt" && ! grep -q "^compose build" "$T/out.txt" && ! grep -q "image prune" "$T/out.txt"'
touch "$T/tag-fehler"
zurueck_lage "$ZI_SHA" "$ZC_SHA"; RC=0; zurueck || RC=$?
ok "Notfall-Rückfall, gemerktes Image lässt sich nicht taggen: Abbruch ohne Codewechsel" '[ "$RC" != 0 ] && [ "$(kopf)" = "$ZI_SHA" ] \
  && grep -q "Rückfall abgebrochen" "$T/out.txt" && ! grep -qE "^compose (up|build)" "$T/out.txt" && git -C "$B" diff --quiet HEAD && [ ! -e "$B/.release-abgelehnt" ]'
rm -f "$T/tag-fehler"
touch "$T/kein-vorher"
zurueck_lage "$ZI_SHA" "$ZC_SHA"; zurueck || true
ok "Notfall-Rückfall, gemerktes Image fehlt: Meldung, Bau aus dem alten Bauplan vor dem Codewechsel" '[ "$(kopf)" = "$ZC_SHA" ] \
  && grep -q "release-vorher fehlt" "$T/out.txt" && grep -qx "compose build app" "$T/out.txt" && grep -qx "bau-stand $ZI_SHA app-alt # Update 5" "$T/out.txt" \
  && grep -qx "compose up -d --force-recreate app" "$T/out.txt"'
touch "$T/bau-fehler"
zurueck_lage "$ZI_SHA" "$ZC_SHA"; RC=0; zurueck || RC=$?
ok "Notfall-Rückfall, Bau scheitert: Abbruch ohne Codewechsel" '[ "$RC" != 0 ] && [ "$(kopf)" = "$ZI_SHA" ] && grep -q "Rückfall abgebrochen" "$T/out.txt" \
  && ! grep -q "^compose up" "$T/out.txt" && git -C "$B" diff --quiet HEAD && [ ! -e "$B/.release-abgelehnt" ]'
rm -f "$T/bau-fehler" "$T/kein-vorher"
cp "$T/env.ohne" "$B/.env"
zurueck_lage "$ZI_SHA" "$ZC_SHA"; zurueck || true
ok "Notfall-Rückfall, Image unterscheidet sich ohne COMPOSE_FILE: weder Tag noch Bau noch neue Container" '[ "$(kopf)" = "$ZC_SHA" ] && ! grep -qE "^(compose|docker)" "$T/out.txt"'

# Bereitstellung: geänderte Datei → neue Adresse (Browser lädt sie sofort), nur aus Git-Objekten, Nachholen, Übergang
git -C "$B" reset -q --hard "$ZC_SHA"; python3 "$B/deploy/bereitstellen.py" >/dev/null
V0=$(vnr frontend.js); export V0   # in den Prüfausdrücken verwendet
JS_SHA=$(commit js-geaendert x "echo '/* neu */' >> '$T/src/app/assets/frontend.js'")
printf '{"release":"%s","ci_ok":["%s"]}' "$JS_SHA" "$JS_SHA" > "$T/state.json"
lauf || true
ok "Skript geändert: Seite verweist nach dem Release auf eine neue Adresse" '[ "$(kopf)" = "$JS_SHA" ] && [ "$(vnr frontend.js)" != "$V0" ] \
  && seite "" | grep -q "assets/frontend.js?v=$(vnr frontend.js)\"" && ! seite "" | grep -q "frontend.js?v=$V0"'
# Veränderungen im Arbeitsordner werden nie in die Liste übernommen und nicht überschrieben (Dateiprüfung meldet sie)
cp "$LISTE" "$T/liste.vorher"
echo "/* fremd */" >> "$B/app/assets/theme.js"; echo "<?php system(\$_GET['c']);" > "$B/app/api/hinten.php"
rm "$LISTE"; RC=0; python3 "$B/deploy/bereitstellen.py" > "$T/out.txt" 2>&1 || RC=$?
ok "Bereitstellung liest den Commit: veränderte/neue Dateien nicht in der Liste, nicht überschrieben" 'cmp -s "$LISTE" "$T/liste.vorher" && ! grep -q hinten.php "$LISTE" \
  && grep -q "fremd" "$B/app/assets/theme.js" && [ "$RC" = 1 ] && grep -q "assets/theme.js: weicht vom Commit ab" "$T/out.txt"'
ok "Prüfung erkennt die Veränderung" '! python3 "$B/deploy/bereitstellen.py" --pruefen >/dev/null'
git -C "$B" checkout -q -- app/assets/theme.js; rm -f "$B/app/api/hinten.php"
# Fehlende Liste und Seiten ohne Nummern (z. B. erster Release noch mit dem alten Skript, „git reset“ von Hand) nachholen
git -C "$B" checkout -q -- app/index.html app/admin/index.html; rm "$LISTE"
ok "Testvoraussetzung: Liste fehlt, Seiten ohne Versionsnummern" '[ ! -e "$LISTE" ] && ! seite "" | grep -q "?v=" && ! python3 "$B/deploy/bereitstellen.py" --pruefen >/dev/null'
python3 "$B/deploy/bereitstellen.py" > "$T/out.txt" 2>&1
ok "fehlende Liste und Nummern nachgeholt (identisch)" 'cmp -s "$LISTE" "$T/liste.vorher" && seite "" | grep -q "frontend.js?v=$(vnr frontend.js)\"" && grep -q "Bereitgestellt für" "$T/out.txt"'
python3 "$B/deploy/bereitstellen.py" > "$T/out.txt" 2>&1
ok "erneuter Aufruf ohne Abweichung: schreibt nichts, meldet nichts" '[ ! -s "$T/out.txt" ]'
# Dashboard neben app/: Abweichungen dort lassen Prüfliste und Seiten unter app/ unberührt
mv "$B/dashboard/index.html" "$T/dashboard-index.weg"; rm "$LISTE"; RC=0; python3 "$B/deploy/bereitstellen.py" > "$T/out.txt" 2>&1 || RC=$?
ok "Dashboard-Seite fehlt: Prüfliste trotzdem geschrieben, Abweichung gemeldet" '[ "$RC" = 1 ] && cmp -s "$LISTE" "$T/liste.vorher" && grep -q "dashboard/index.html: fehlt" "$T/out.txt"'
mv "$T/dashboard-index.weg" "$B/dashboard/index.html"
ok "Dashboard wieder vollständig: Prüfung ohne Abweichung" 'python3 "$B/deploy/bereitstellen.py" --pruefen >/dev/null'
ok "aktualisieren.sh holt die Bereitstellung vor dem Release-Modus nach" 'awk "!b && /^ *python3 deploy.bereitstellen.py/{b=NR} /^ *exec sh deploy.freigabe-einspielen.sh/{f=NR} END{exit !(b && f && b < f)}" "$B/deploy/aktualisieren.sh"'
# Übergang: Stand mit Liste und Nummern im Repository (vor der Umstellung) ↔ Stand ohne
ALT_SHA=$(commit alt-mit-liste x "cd '$T/src' && python3 deploy/bereitstellen.py --verzeichnis app >/dev/null && git add -f app/api/lib/integritaet-liste.php")
NEU_SHA=$(commit neu-ohne-liste x "cd '$T/src' && git rm -q --cached app/api/lib/integritaet-liste.php && rm app/api/lib/integritaet-liste.php && python3 werkzeuge/asset_versionen.py --setzen >/dev/null && echo '<!-- neu -->' >> app/index.html")
printf '{"release":"%s","ci_ok":["%s"]}' "$ALT_SHA" "$ALT_SHA" > "$T/state.json"
lauf || true
ok "Stand mit eigener Liste: unverändert aus dem Commit, nichts erzeugt" '[ "$(kopf)" = "$ALT_SHA" ] && [ "$(st ok)" = True ] && git -C "$B" diff --quiet HEAD \
  && ! grep -q "aus Commit" "$LISTE" && python3 "$B/deploy/bereitstellen.py" --pruefen | grep -q "selbst mit"'
printf '{"release":"%s","ci_ok":["%s"]}' "$NEU_SHA" "$NEU_SHA" > "$T/state.json"
lauf || true
ok "danach Stand ohne Liste: Liste erzeugt, Nummern gesetzt" '[ "$(kopf)" = "$NEU_SHA" ] && [ "$(st ok)" = True ] && grep -q "aus Commit $NEU_SHA" "$LISTE" \
  && seite "" | grep -q "frontend.js?v=$(vnr frontend.js)\"" && python3 "$B/deploy/bereitstellen.py" --pruefen >/dev/null'
zurueck || true
ok "Notfall-Rückfall auf den Stand mit Liste: dessen Liste und Seiten wieder aktiv" '[ "$(kopf)" = "$ALT_SHA" ] && git -C "$B" diff --quiet HEAD && ! grep -q "aus Commit" "$LISTE" \
  && [ -z "$(git -C "$B" status --porcelain --ignored -- app/api/lib)" ]'
H_SHA=$ALT_SHA   # aktueller Stand für die folgenden Prüfungen

# Active SQLite must never be silently opened by an old file-only release.
L_SHA=$(commit ohne-sqlite x "rm '$T/src/app/api/storage.php'")
kill "$WEB_PID"; wait "$WEB_PID" 2>/dev/null || true
python3 "$B/deploy/datenbank.py" migrate "$B/daten" --offline >/dev/null
(cd "$B/app" && exec php -S 127.0.0.1:$WEB_PORT >/dev/null 2>&1) & WEB_PID=$!
printf '{"release":"%s","ci_ok":["%s"]}' "$L_SHA" "$L_SHA" > "$T/state.json"
lauf || true
ok "SQLite: inkompatiblen Release vor Codewechsel abweisen" '[ "$(kopf)" = "$H_SHA" ] && grep -q "SQLite aktiv" "$T/out.txt"'
printf '%s\n{"vorher":"%s"}' '<?php http_response_code(404); exit; ?>' "$L_SHA" > "$B/daten/deployment.php"
printf '%s\n' "$L_SHA" > "$B/.release-vorher"
sh "$B/deploy/release-zurueck.sh" > "$T/out.txt" 2>&1 || true
ok "SQLite: auch manueller Code-Rückfall ist gesperrt" '[ "$(kopf)" = "$H_SHA" ] && grep -q "SQLite aktiv" "$T/out.txt"'

echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" -eq 0 ]
