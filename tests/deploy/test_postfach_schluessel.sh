#!/bin/sh
# Test von deploy/postfach-schluessel.sh (Schlüssel des Postfach-Passworts aus dem gemeinsamen Datenordner, ADR-007) – in einem
# Wegwerf-Ordner, ohne root (Besitzer wird nur versucht zu setzen) – und dass die Anwendung den Schlüssel an beiden Orten findet.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
AUS=""; CODE=0
export AUS CODE
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
G='<?php http_response_code(404); exit; ?>'
mkdir -p "$T/daten"
printf '#!/bin/sh\necho "$*" >> "%s/aufrufe"\n[ ! -f "%s/compose-fehler" ]\n' "$T" "$T" > "$T/compose"; chmod +x "$T/compose"
export COMPOSE="$T/compose"
cd "$T"
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" status) && CODE=0 || CODE=$?
ok "status ohne Schlüssel: Zugangsdaten aus .env" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Kein Schlüssel"'
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" umziehen) && CODE=0 || CODE=$?
ok "umziehen ohne Schlüssel: nichts zu tun, Ordner trotzdem angelegt (nur Besitzer), kein Aufruf" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Nichts umzuziehen" && [ "$(stat -c %a daten-geheim)" = 700 ] && [ ! -f aufrufe ]'
rmdir daten-geheim
printf '%s\n{"key":"YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=","created":"2026-11-04T18:00:00Z"}' "$G" > daten/mail-schluessel.php
cp daten/mail-schluessel.php "$T/original"
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" status)
ok "status: noch im Datenordner, mit Hinweis auf umziehen" 'echo "$AUS" | grep -q "noch im gemeinsamen Datenordner" && echo "$AUS" | grep -q "umziehen"'
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" umziehen) && CODE=0 || CODE=$?
ok "umziehen: Schlüssel unverändert in daten-geheim, im Datenordner entfernt" '[ $CODE = 0 ] && cmp -s original daten-geheim/mail-schluessel.php && [ ! -e daten/mail-schluessel.php ]'
ok "umziehen: Passwörter danach im Dienst postausgang gebunden (v2)" 'grep -qx "exec -T postausgang php /var/www/html/api/postausgang.php --umschluesseln" aufrufe'
ok "umziehen: nur für den Besitzer lesbar, keine Zwischendatei" '[ "$(stat -c %a daten-geheim/mail-schluessel.php)" = 600 ] && [ "$(stat -c %a daten-geheim)" = 700 ] && [ ! -e daten-geheim/mail-schluessel.php.neu ]'
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" status)
ok "status: in daten-geheim" 'echo "$AUS" | grep -q "in daten-geheim (nicht für die Kundenseite lesbar)" && ! echo "$AUS" | grep -q Achtung'
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" umziehen)
ok "umziehen ein zweites Mal: Schlüssel bleibt, Bindung erneut geprüft" 'echo "$AUS" | grep -q "bereits in daten-geheim" && cmp -s original daten-geheim/mail-schluessel.php && [ "$(grep -c umschluesseln aufrufe)" = 2 ]'
touch compose-fehler
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" umziehen 2>&1) && CODE=0 || CODE=$?
ok "Dienst nicht erreichbar: deutlicher Hinweis, Fehlercode" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht gebunden werden"'
rm compose-fehler
touch compose-fehler
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" zurueck 2>&1) && CODE=0 || CODE=$?
ok "zurueck ohne erreichbaren Dienst: Abbruch, Schlüssel bleibt in daten-geheim" '[ $CODE = 1 ] && echo "$AUS" | grep -q "neu eingegeben" && [ ! -e daten/mail-schluessel.php ]'
rm compose-fehler
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" zurueck) && CODE=0 || CODE=$?
ok "zurueck: erst Passwörter auf v1, dann wieder im Datenordner, Kopie in daten-geheim bleibt" '[ $CODE = 0 ] && grep -qx "exec -T postausgang php /var/www/html/api/postausgang.php --entbinden" aufrufe \
  && cmp -s original daten/mail-schluessel.php && cmp -s original daten-geheim/mail-schluessel.php'
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" status)
ok "status: Hinweis auf die zusätzliche Kopie im Datenordner" 'echo "$AUS" | grep -q "Achtung: zusätzlich noch eine Kopie"'
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" umziehen) && CODE=0 || CODE=$?
ok "umziehen bei gleicher Kopie: Datenordner bereinigt" '[ $CODE = 0 ] && [ ! -e daten/mail-schluessel.php ] && cmp -s original daten-geheim/mail-schluessel.php'
printf '%s\n{"key":"YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmI=","created":"2026-11-04T19:00:00Z"}' "$G" > daten/mail-schluessel.php
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" umziehen 2>&1) && CODE=0 || CODE=$?
ok "umziehen bei unterschiedlichen Schlüsseln: Abbruch, nichts verändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "unterschiedliche Schlüssel" && [ -f daten/mail-schluessel.php ] && cmp -s original daten-geheim/mail-schluessel.php'
rm -f daten/mail-schluessel.php
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" vielleicht 2>&1) && CODE=0 || CODE=$?
ok "unbekannter Befehl abgelehnt" '[ $CODE = 2 ]'
mkdir "$T/leer"; cd "$T/leer"
AUS=$(sh "$REPO/deploy/postfach-schluessel.sh" status 2>&1) && CODE=0 || CODE=$?
ok "außerhalb des Installationsordners: Abbruch" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht gefunden"'
cd "$T"

# Anwendung (app/api/mail.php): Schlüssel zuerst aus WA_GEHEIM_DIR, sonst aus dem Datenordner; neuer Schlüssel im eigenen Ordner
if command -v php >/dev/null 2>&1; then
  cat > "$T/probe.php" <<'PHP'
<?php
const WA_API = true;
$DATA = $argv[1];
require $argv[2] . '/app/api/storage.php';
require $argv[2] . '/app/api/mail.php';
$k = mail_key(!empty($argv[3]));
echo $k === null ? 'kein' : base64_encode($k);
PHP
  P="$T/probe.php"
  AUS=$(WA_GEHEIM_DIR="$T/daten-geheim" php "$P" "$T/daten" "$REPO")
  ok "Anwendung liest den Schlüssel aus WA_GEHEIM_DIR" '[ "$AUS" = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=" ]'
  AUS=$(php "$P" "$T/daten" "$REPO")
  ok "ohne WA_GEHEIM_DIR (Kundenseite): kein Schlüssel" '[ "$AUS" = kein ]'
  mv daten-geheim/mail-schluessel.php daten/mail-schluessel.php
  AUS=$(WA_GEHEIM_DIR="$T/daten-geheim" php "$P" "$T/daten" "$REPO")
  ok "noch nicht umgezogen: Anwendung findet ihn im Datenordner" '[ "$AUS" = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=" ]'
  rm -f daten/mail-schluessel.php
  AUS=$(WA_GEHEIM_DIR="$T/daten-geheim" php "$P" "$T/daten" "$REPO" neu)
  ok "neuer Schlüssel landet in WA_GEHEIM_DIR, nicht im Datenordner" '[ "$AUS" != kein ] && [ -f daten-geheim/mail-schluessel.php ] && [ ! -e daten/mail-schluessel.php ] && [ "$(stat -c %a daten-geheim/mail-schluessel.php)" = 600 ]'
  ok "neuer Schlüssel im gleichen Format (Zugriffssperre vorn)" 'head -c 40 daten-geheim/mail-schluessel.php | grep -q "http_response_code(404)"'
fi
echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" = 0 ]
