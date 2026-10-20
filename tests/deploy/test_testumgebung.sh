#!/bin/sh
# Test der Testumgebung-Verwaltung (deploy/testumgebung.sh) mit Platzhaltern für docker und git – ohne Server.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; fi; }
mkdir -p "$T/prod/deploy" "$T/bin"
cp -r "$REPO/deploy/testumgebung.sh" "$REPO/deploy/testumgebung" "$T/prod/deploy/"
printf 'DOMAIN="angebot.example.org"\nMAIL_SMTP_PASS=geheim\n' > "$T/prod/.env"
LOG="$T/aufrufe.log"; export LOG REPO
cat > "$T/bin/docker" <<'S'
#!/bin/sh
echo "docker $*" >> "$LOG"
case "$*" in
  "compose ps -q caddy") echo caddy123 ;;
  "network inspect wochenangebot-edge") [ -z "${EDGE_FEHLT:-}" ] || exit 1 ;;
  inspect*) echo wochenangebot_default ;;
  run*) cat >/dev/null; printf '%s' '$2y$10$abcdefghijklmnopqrstuv' ;;
esac
S
cat > "$T/bin/git" <<'S'
#!/bin/sh
echo "git $*" >> "$LOG"
case "$1" in
  clone) mkdir -p "$4/.git" "$4/tests/fixtures"; cp -r "$REPO/tests/fixtures/data-seed" "$4/tests/fixtures/" ;;
  -C) case "$3" in fetch) case "$*" in *gibtsnicht*) exit 1 ;; esac ;; log) echo "abc123 Testcommit" ;; esac ;;
esac
S
chmod +x "$T/bin/docker" "$T/bin/git"
export PATH="$T/bin:$PATH" WA_TEST_DIR="$T/test"
run() { sh "$T/prod/deploy/testumgebung.sh" "$@"; }

ok "Einrichten ohne Netz wochenangebot-edge abgelehnt (Echtbetrieb zu alt)" '! (printf "test\nSicheres-Testpw-1\nSicheres-Testpw-1\n" | EDGE_FEHLT=1 run einrichten > "$T/out" 2>&1) && grep -q "wochenangebot-edge" "$T/out"'
printf 'test\nSicheres-Testpw-1\nSicheres-Testpw-1\n' | run einrichten > "$T/out" 2>&1
ok "Einrichten: Testadresse aus dem Echtbetrieb, kein Produktivnetz mehr" 'grep -qx "TEST_DOMAIN=test.angebot.example.org" "$T/test/.env" && ! grep -q PROD_NETWORK "$T/test/.env"'
ok "Testumgebung nur im Netz wochenangebot-edge, Proxy nur Caddy" 'grep -q "name: wochenangebot-edge" "$T/test/docker-compose.yml" && grep -q "networks: \[edge\]" "$T/test/docker-compose.yml" && ! grep -q PROD_NETWORK "$T/test/docker-compose.yml" && grep -q "WA_TRUSTED_PROXIES: wa-caddy" "$T/test/docker-compose.yml"'
ok "Echtbetrieb: App nicht im Netz edge, Caddy schon" 'sed -n "/^  app:/,/^  caddy:/p" "$REPO/docker-compose.yml" > "$T/app.yml"; sed -n "/^  caddy:/,/^volumes:/p" "$REPO/docker-compose.yml" > "$T/caddy.yml"; ! grep -q "networks" "$T/app.yml" && grep -q "WA_TRUSTED_PROXIES: caddy" "$T/app.yml" && grep -q "edge:" "$T/caddy.yml"'
ok "Einrichten: keine Geheimnisse des Echtbetriebs übernommen" '! grep -q geheim "$T/test/.env"'
ok "Einrichten: Passwortschutz als Hash" 'grep -qx "test:\$2y\$10\$abcdefghijklmnopqrstuv" "$T/test/zugang.htpasswd"'
ok "Einrichten: Passwort nicht in Aufrufparametern" '! grep -q Sicheres-Testpw "$LOG"'
ok "Einrichten: Testdaten angelegt, Vorlagen kopiert" '[ -f "$T/test/daten/angebot.php" ] && [ -f "$T/test/docker-compose.yml" ] && [ -f "$T/test/apache-schutz.conf" ]'
ok "Einrichten: Container gestartet" 'grep -q "compose --project-directory $T/test -f $T/test/docker-compose.yml up -d" "$LOG"'
printf 'x\nkurz\nkurz\n' > "$T/in"; rm "$T/test/zugang.htpasswd"
ok "Zu kurzes Passwort abgelehnt" '! run passwort < "$T/in" >/dev/null 2>&1 && [ ! -f "$T/test/zugang.htpasswd" ]'
ok "Einspielen ohne Zweig abgelehnt" '! run einspielen >/dev/null 2>&1'
ok "Einspielen mit ungültigem Namen abgelehnt" '! run einspielen "../x" >/dev/null 2>&1 && ! run einspielen "-x" >/dev/null 2>&1 && ! run einspielen "a b" >/dev/null 2>&1'
ok "Unbekannter Zweig abgelehnt" '! run einspielen gibtsnicht >/dev/null 2>&1'
: > "$LOG"; run einspielen feature/neu > "$T/out" 2>&1
ok "Einspielen: nur Zweig des eigenen Repositorys" 'grep -q "fetch -q origin +refs/heads/feature/neu:refs/remotes/origin/feature/neu" "$LOG" && grep -q "checkout -q --detach origin/feature/neu" "$LOG"'
ok "Einspielen: Testdaten bleiben" '[ -f "$T/test/daten/angebot.php" ]'
ok "Einspielen: Container neu erstellt (übernimmt Netzwechsel)" 'grep -q "up -d --force-recreate" "$LOG"'
echo extra > "$T/test/daten/notiz.php"
echo nein | run zuruecksetzen >/dev/null 2>&1 || true
ok "Zurücksetzen nur nach Bestätigung" '[ -f "$T/test/daten/notiz.php" ]'
echo ja | run zuruecksetzen >/dev/null 2>&1
ok "Zurücksetzen legt Testdaten neu an" '[ ! -f "$T/test/daten/notiz.php" ] && [ -f "$T/test/daten/angebot.php" ]'
echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" -eq 0 ]
