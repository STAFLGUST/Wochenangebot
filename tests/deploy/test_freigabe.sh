#!/bin/sh
# Integrationstest des Release-Modus (deploy/freigabe-einspielen.sh) – komplett lokal:
# eigenes Git-„origin“, GitHub-API-Ersatz, PHP-Testserver als Live-Seite, echte Datensicherung.
# Prüft: kein Release → nichts passiert; freigegebener Commit geht live; defekter Release wird erkannt und
# automatisch zurückgesetzt (und nicht erneut versucht); Release ohne CI und Commit außerhalb von main werden abgelehnt.
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
python3 "$REPO/tests/deploy/github_stub.py" $API_PORT "$T/state.json" & API_PID=$!
(cd "$B/app" && exec php -S 127.0.0.1:$WEB_PORT >/dev/null 2>&1) & WEB_PID=$!
sleep 1
lauf() { WA_BASIS="$B" WA_API="http://127.0.0.1:$API_PORT" WA_HEALTH_URL="http://127.0.0.1:$WEB_PORT" WA_HEALTH_HOST="test.local:80:127.0.0.1" \
         WA_COMPOSE="echo compose" sh "$B/deploy/freigabe-einspielen.sh" > "$T/out.txt" 2>&1; rc=$?; [ -z "${DEBUG:-}" ] || { echo "--- rc=$rc"; cat "$T/out.txt"; }; return $rc; }
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
