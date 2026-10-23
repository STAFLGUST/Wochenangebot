#!/bin/sh
# Test von „konten.sh pruefen“ (Anmeldeprobleme erkennen) – mit Platzhalter für kcadm und einer lokalen Zeitquelle, ohne Docker.
# Das Zusammenspiel mit echtem Keycloak prüft tests/oidc/test_oidc.py.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d)
ZPID=
trap '[ -n "$ZPID" ] && kill "$ZPID" 2>/dev/null; rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }

# Platzhalter für kcadm: antwortet je nach Pfad mit den Dateien aus $T/kc/ und protokolliert jeden Aufruf
mkdir -p "$T/kc" "$T/inst"
cat > "$T/kcadm" <<'SH'
#!/bin/sh
echo "$*" >> "$KC_DIR/aufrufe"
case "$1 $2" in
  "get users") echo "abc-123" ;;
  "get users/abc-123") cat "$KC_DIR/konto" ;;
  "get users/abc-123/credentials") cat "$KC_DIR/faktoren" ;;
  "get attack-detection/brute-force/users/abc-123") cat "$KC_DIR/sperre" ;;
  "get events") cat "$KC_DIR/ereignisse" ;;
  "get realms/mitarbeiter") cat "$KC_DIR/realm" ;;
  "get authentication/flows/mitarbeiter-browser/executions") cat "$KC_DIR/ablauf" ;;
  "get authentication/config/c-pwd") echo '{"id":"c-pwd","config":{"default.reference.value":"pwd","default.reference.maxAge":"36000"}}' ;;
  "get authentication/config/c-otp") echo '{"id":"c-otp","config":{"default.reference.value":"otp","default.reference.maxAge":"36000"}}' ;;
  "get clients") c=$(printf '%s\n' "$@" | sed -n 's/^clientId=//p'); [ -f "$KC_DIR/client-$c" ] && echo "id-$c" ;;
  "get clients/id-"*)
    c=${2#clients/id-}; c=${c%%/*}
    case "$2" in */protocol-mappers/models) cat "$KC_DIR/mapper-$c" ;; *) cat "$KC_DIR/client-$c" ;; esac ;;
  *) echo "unerwartet: $*" >&2; exit 1 ;;
esac
SH
chmod +x "$T/kcadm"
export KCADM="$T/kcadm" KC_DIR="$T/kc" KC_ADMIN_PASSWORD_TEST=test-nur-lokal
echo 'DOMAIN=angebot-stafl.de' > "$T/inst/.env"

# Zeitquelle mit einstellbarer Abweichung (Sekunden in $T/abweichung)
cat > "$T/zeit.py" <<'PY'
import http.server, os, sys, time
from email.utils import formatdate
class H(http.server.BaseHTTPRequestHandler):
    def date_time_string(self, timestamp=None):
        return formatdate(time.time() + float(open(sys.argv[2]).read()), usegmt=True)
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def log_message(self, *a):
        pass
s = http.server.HTTPServer(('127.0.0.1', 0), H)
open(sys.argv[1], 'w').write(str(s.server_port))
s.serve_forever()
PY
echo 0 > "$T/abweichung"
python3 "$T/zeit.py" "$T/port" "$T/abweichung" & ZPID=$!
i=0; while [ ! -s "$T/port" ] && [ $i -lt 50 ]; do sleep 0.1; i=$((i + 1)); done
export ZEIT_QUELLE; ZEIT_QUELLE="http://127.0.0.1:$(cat "$T/port")/"

jetzt_ms=$(($(date +%s) * 1000))
# Fall 1: alles in Ordnung (ein Einmalcode-Gerät, keine Sperre, erfolgreiche Anmeldung)
echo '{"enabled": true, "requiredActions": []}' > "$T/kc/konto"
echo "[{\"type\":\"password\",\"createdDate\":$jetzt_ms},{\"type\":\"otp\",\"createdDate\":$jetzt_ms,\"userLabel\":\"Telefon\",\"secretData\":\"GEHEIM-DARF-NICHT-ERSCHEINEN\"}]" > "$T/kc/faktoren"
echo '{"numFailures": 0, "disabled": false, "lastFailure": 0}' > "$T/kc/sperre"
echo "[{\"time\":$jetzt_ms,\"type\":\"LOGIN\",\"clientId\":\"dashboard\",\"ipAddress\":\"192.0.2.10\"}]" > "$T/kc/ereignisse"
echo '{"otpPolicyPeriod": 30, "otpPolicyLookAheadWindow": 1, "otpPolicyCodeReusable": false, "failureFactor": 5, "eventsEnabled": true}' > "$T/kc/realm"
ok_ablauf='[{"providerId":"auth-cookie","level":0},{"providerId":"auth-username-password-form","level":2,"requirement":"REQUIRED","authenticationConfig":"c-pwd"},{"providerId":"auth-otp-form","level":3,"requirement":"REQUIRED","authenticationConfig":"c-otp"},{"providerId":"auth-otp-form","level":4,"requirement":"REQUIRED","authenticationConfig":"c-otp"}]'
echo "$ok_ablauf" > "$T/kc/ablauf"
for c in dashboard verwaltung; do
  echo '{"attributes":{"default.acr.values":"pwd"}}' > "$T/kc/client-$c"
  echo '[{"protocolMapper":"oidc-amr-mapper","config":{"id.token.claim":"true"}}]' > "$T/kc/mapper-$c"
done
cd "$T/inst"
export AUS CODE; AUS=$(sh "$REPO/deploy/anmeldung/konten.sh" pruefen Admin 2>&1) && CODE=0 || CODE=$?
ok "unauffälliges Konto: Erfolg, keine Hinweise" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Keine Auffälligkeiten gefunden"'
ok "Name wird klein geschrieben gesucht" 'grep -q "username=admin" "$T/kc/aufrufe"'
ok "Faktoren mit Bezeichnung, nie Geheimnisse" 'echo "$AUS" | grep -q "Einmalcode (App): eingerichtet .*„Telefon“" && ! echo "$AUS" | grep -q GEHEIM'
ok "Einmalcode-Regeln verständlich" 'echo "$AUS" | grep -q "jeder Code nur einmal"'
ok "Ereignis mit Anwendung und Adresse" 'echo "$AUS" | grep -q "LOGIN · über dashboard · von 192.0.2.10"'
ok "Uhr mit der Zeitquelle verglichen" 'echo "$AUS" | grep -Eq "Abweichung gegenüber http://127.0.0.1:[0-9]+/: [+-][0-1] s"'
ok "nur lesende Aufrufe an Keycloak" '! grep -Ev "^get " "$T/kc/aufrufe"'
ok "Anmeldeablauf: Passwort und Einmalcode melden ihre Methode" 'echo "$AUS" | grep -q "Passwort (Ebene 2, REQUIRED): meldet .pwd., gültig 36000 s" && [ "$(echo "$AUS" | grep -c "Einmalcode (Ebene [34], REQUIRED): meldet .otp.")" = 2 ]'
ok "Anwendungen mit amr-Claim, nicht vorhandene Anwendungen ausgelassen" 'echo "$AUS" | grep -q "dashboard: amr-Claim im Anmelde-Token · Standard-Stufe pwd" && echo "$AUS" | grep -q "verwaltung: amr-Claim im Anmelde-Token" && ! echo "$AUS" | grep -q "bestand:"'

# Fall 2: zwei Einmalcode-Geräte, Fehlversuche mit Sperre, falscher Code, Uhr 2 Minuten falsch
echo "[{\"type\":\"password\",\"createdDate\":$jetzt_ms},{\"type\":\"otp\",\"createdDate\":$jetzt_ms},{\"type\":\"otp\",\"createdDate\":$jetzt_ms,\"userLabel\":\"Neu\"}]" > "$T/kc/faktoren"
echo "{\"numFailures\": 3, \"disabled\": true, \"lastFailure\": $jetzt_ms}" > "$T/kc/sperre"
echo "[{\"time\":$jetzt_ms,\"type\":\"LOGIN_ERROR\",\"error\":\"invalid_user_credentials\",\"details\":{\"credential_type\":\"otp\"},\"clientId\":\"angebot\"},{\"time\":$jetzt_ms,\"type\":\"LOGIN_ERROR\",\"error\":\"etwas_neues\"}]" > "$T/kc/ereignisse"
echo 120 > "$T/abweichung"
# … außerdem: Einmalcode der ersten Stufe ohne gemeldete Methode, Client ohne amr-Claim (Ursache der doppelten Code-Abfrage)
echo '[{"providerId":"auth-username-password-form","level":2,"requirement":"REQUIRED","authenticationConfig":"c-pwd"},{"providerId":"auth-otp-form","level":3,"requirement":"REQUIRED"}]' > "$T/kc/ablauf"
echo '{"attributes":{}}' > "$T/kc/client-bestand"; echo '[]' > "$T/kc/mapper-bestand"
echo '{}' > "$T/kc/client-angebot"; echo '[{"protocolMapper":"oidc-amr-mapper","config":{"id.token.claim":"false"}}]' > "$T/kc/mapper-angebot"
AUS=$(sh "$REPO/deploy/anmeldung/konten.sh" pruefen admin 2>&1) && CODE=0 || CODE=$?
ok "Sperre erkannt, Befehl zum Entsperren genannt" '[ $CODE = 0 ] && echo "$AUS" | grep -q "JA, vorübergehend gesperrt" && echo "$AUS" | grep -q "Fehlversuche in Folge: 3 (Grenze 5)" && echo "$AUS" | grep -q "konten.sh entsperren admin"'
ok "mehrere Einmalcode-Geräte als Ursache genannt" 'echo "$AUS" | grep -q "2 Einmalcode-Geräte eingerichtet"'
ok "Fehlerursache auf Deutsch, Schritt Einmalcode" 'echo "$AUS" | grep -q "LOGIN_ERROR · Passwort oder Einmalcode falsch.* · Schritt: otp · über angebot"'
ok "unbekannter Fehler unverändert angezeigt" 'echo "$AUS" | grep -q "LOGIN_ERROR · etwas_neues"'
ok "falsch gehende Serveruhr gemeldet" 'echo "$AUS" | grep -Eq "Serveruhr weicht -1[12][0-9] s ab"'
ok "Einmalcode ohne gemeldete Methode erkannt, Abhilfe genannt" 'echo "$AUS" | grep -q "Einmalcode (Ebene 3, REQUIRED): meldet NICHTS" && echo "$AUS" | grep -q "fragt den zweiten Faktor ein zweites Mal ab. Abhilfe: sh deploy/anmeldung/konten.sh realm-aktualisieren"'
ok "Client ohne bzw. mit abgeschaltetem amr-Claim erkannt" 'echo "$AUS" | grep -q "bestand: amr-Claim FEHLT" && echo "$AUS" | grep -q "angebot: amr-Claim vorhanden, aber NICHT im Anmelde-Token" && echo "$AUS" | grep -q "Client bestand: Anmeldemethoden fehlen"'

# Fall 3: Konto gesperrt, keine Ereignisse, Zeitquelle nicht erreichbar
echo '{"enabled": false, "requiredActions": ["UPDATE_PASSWORD"]}' > "$T/kc/konto"
echo '[]' > "$T/kc/ereignisse"
echo '{"otpPolicyPeriod": 30, "eventsEnabled": false}' > "$T/kc/realm"
AUS=$(ZEIT_QUELLE=http://127.0.0.1:9/ sh "$REPO/deploy/anmeldung/konten.sh" pruefen admin 2>&1) && CODE=0 || CODE=$?
ok "gesperrtes Konto und offene Schritte" '[ $CODE = 0 ] && echo "$AUS" | grep -q "GESPERRT (konten.sh entsperren)" && echo "$AUS" | grep -q "offene Schritte .*UPDATE_PASSWORD"'
ok "ohne Ereignisprotokoll verständlich" 'echo "$AUS" | grep -q "keine gespeichert (Ereignisprotokoll ist aus)"'
ok "ohne Zeitquelle kein Abbruch" '! echo "$AUS" | grep -q "Abweichung gegenüber"'

# Aufruffehler
AUS=$(sh "$REPO/deploy/anmeldung/konten.sh" pruefen 2>&1) && CODE=0 || CODE=$?
ok "ohne Namen: Aufrufhinweis" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Aufruf: konten.sh pruefen <benutzername>"'
AUS=$(sh "$REPO/deploy/anmeldung/konten.sh" pruefen 'x; rm -rf /' 2>&1) && CODE=0 || CODE=$?
ok "ungültiger Name abgelehnt, bevor Keycloak gefragt wird" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Benutzername:"'

echo "konten.sh pruefen: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
