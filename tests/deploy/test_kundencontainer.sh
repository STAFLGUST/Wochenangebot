#!/usr/bin/env bash
# Gehärteter Kundencontainer (ADR-007, „Härtung des Kundencontainers“) mit echtem Docker – Einstellungen genau aus
# docker-compose.yml und deploy/anmeldung/docker-compose.anmeldung.yml (Dienst app), Image stafl-app:<WA_BILD_VERSION>
# (Standard „pruefung“, gebaut von deploy/image/pruefen.sh; lokal: docker build -t stafl-app:pruefung deploy/image).
#
# Prüft: läuft als www-data ohne Linux-Sonderrechte, keine Rechteausweitung, Dateisystem nur lesbar, /tmp und /run ohne
# Ausführung, nur im Netz „kunde“ ohne Ausgang ins Internet (auch kein DNS nach außen); einziger Weg nach außen ist das
# Caddy-Relais der Datenleck-Prüfung (Block aus dem echten Caddyfile, nur GET /range/<5 Hex-Zeichen>); PHP nur für die
# Kundenseite eingeschränkt (keine Programme, keine Uploads, Dateien nur unter der Anwendung und /tmp, Version verborgen),
# Erweiterungen des Images unverändert; Apache ohne Version und ohne TRACE; die Kundenseite arbeitet trotzdem: Startseite,
# Status, Angebot, Kundenanmeldung (Fehlversuch mit Sitzung und Schreiben in den Datenordner), keine Fehler im Protokoll.
# Der Abruf bei api.pwnedpasswords.com wird nur geprüft, wenn das Netz des Runners ihn erlaubt (in der CI ja).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
V="${WA_BILD_VERSION:-pruefung}"
BILD="stafl-app:$V"
CADDY="$(sed -n 's/^ *image: *\(caddy:[^ ]*\).*$/\1/p' "$REPO/docker-compose.yml")"
P="wa-kunde-$$"
T="$(mktemp -d)"
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; printf '%s\n' "${AUS:-}" | tail -5 | sed 's/^/    /'; fi; }
dc() { docker compose --project-directory "$T" -p "$P" --env-file "$T/.env" -f "$REPO/docker-compose.yml" -f "$REPO/deploy/anmeldung/docker-compose.anmeldung.yml" "$@"; }
aufraeumen() {
  docker rm -f "$P-relais" >/dev/null 2>&1 || true
  dc down -v --remove-orphans >/dev/null 2>&1 || true
  docker network rm "$P-aussen" >/dev/null 2>&1 || true
  docker run --rm --user 0 -v "$T:/t" "$BILD" chmod -R a+rwX /t >/dev/null 2>&1 || true   # Dateien von www-data im Datenordner
  rm -rf "$T"
}
trap aufraeumen EXIT
docker image inspect "$BILD" >/dev/null 2>&1 || { echo "FAIL Image $BILD fehlt (deploy/image/pruefen.sh baut es)"; exit 1; }

# Arbeitsordner wie der Installationsordner: Anwendung (Kopie mit Prüfseite), Testdaten, Härtungsdateien
cp -r "$REPO/app" "$T/app"
cat > "$T/app/kunde-haertung-probe.php" <<'PHP'
<?php
header('Content-Type: application/json');
$ziel = sprintf((string)getenv('WA_PWNED_URL'), '21BD1');
$ctx = stream_context_create(['http' => ['timeout' => 8]]);
$antwort = @file_get_contents($ziel, false, $ctx);
echo json_encode([
  'uid' => function_exists('posix_getuid') ? posix_getuid() : null,
  'disable' => ini_get('disable_functions'),
  'exec' => function_exists('exec'), 'proc_open' => function_exists('proc_open'), 'mail' => function_exists('mail'),
  'open_basedir' => ini_get('open_basedir'), 'etc_passwd' => @is_readable('/etc/passwd'),
  'uploads' => ini_get('file_uploads'), 'expose' => ini_get('expose_php'), 'display' => ini_get('display_errors'),
  'url_include' => ini_get('allow_url_include'), 'pwned_url' => $ziel,
  'pwned' => is_string($antwort) ? (strpos($antwort, ':') !== false ? 'ok' : 'leer') : 'fehler',
]);
PHP
cp -r "$REPO/tests/fixtures/data-seed" "$T/daten"; chmod -R a+rwX "$T/daten"
mkdir -p "$T/deploy/anmeldung"; cp "$REPO/deploy/anmeldung/kunde-php.ini" "$REPO/deploy/anmeldung/kunde-apache.conf" "$T/deploy/anmeldung/"
cat > "$T/.env" <<EOF
DOMAIN=angebot-stafl.de
STAFL_APP_VERSION=$V
OIDC_SECRET_DASHBOARD=nur-test
OIDC_SECRET_ANGEBOT=nur-test
OIDC_CRYPTO_DASHBOARD=nur-test
OIDC_CRYPTO_ANGEBOT=nur-test
KC_DB_PASSWORD=nur-test
KUNDEN_CPUS=1
EOF

AUS=$(dc up -d --no-build --pull never app 2>&1) || { echo "FAIL Kundencontainer startet nicht"; echo "$AUS"; exit 1; }
C="$(dc ps -q app)"
for _ in $(seq 1 30); do docker exec "$C" sh -c 'test -s /run/apache2/apache2.pid' 2>/dev/null && break; sleep 1; done
NETZ="${P}_kunde"
# Relais aus dem echten Caddyfile in einem eigenen Caddy (Alias „caddy“ im Netz „kunde“, Ausgang über ein zweites Netz wie im Betrieb)
python3 - "$REPO/Caddyfile" "$T/Caddyfile.relais" <<'PY'
import re, sys
c = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"^http://:8081 \{\n.*?^\}\n", c, re.MULTILINE | re.DOTALL)
open(sys.argv[2], "w", encoding="utf-8").write("{\n\tadmin off\n}\n\n" + (m.group(0) if m else ""))
PY
docker network create "$P-aussen" >/dev/null
docker run -d --name "$P-relais" --network "$NETZ" --network-alias caddy -v "$T/Caddyfile.relais:/etc/caddy/Caddyfile:ro" "$CADDY" >/dev/null
docker network connect "$P-aussen" "$P-relais"
klient() { docker run --rm --network "$NETZ" "$BILD" "$@"; }
for _ in $(seq 1 30); do klient curl -s -o /dev/null "http://app/" 2>/dev/null && break; sleep 1; done
for _ in $(seq 1 20); do klient curl -s -o /dev/null "http://caddy:8081/" 2>/dev/null && break; sleep 1; done

# ── Einstellungen des Containers (aus den Compose-Dateien) ──
I() { docker inspect -f "$1" "$C"; }
AUS="$(I '{{.Config.User}} {{json .HostConfig.CapDrop}} {{.HostConfig.ReadonlyRootfs}} {{json .HostConfig.SecurityOpt}} {{json .HostConfig.Sysctls}}')"
ok "Compose: www-data, alle Sonderrechte entzogen, nur lesbar, keine Rechteausweitung, Port 80 ohne root" \
  '[ "$AUS" = "33:33 [\"ALL\"] true [\"no-new-privileges:true\"] {\"net.ipv4.ip_unprivileged_port_start\":\"0\"}" ]'
AUS="$(I '{{json .HostConfig.Tmpfs}}')"
ok "Compose: /tmp und /run ohne Ausführung (noexec, nosuid, nodev)" 'echo "$AUS" | grep -q "\"/tmp\":\"[^\"]*noexec,nosuid,nodev" && echo "$AUS" | grep -q "\"/run\":\"[^\"]*noexec,nosuid,nodev"'
AUS="$(I '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
ok 'nur im Netz kunde (nicht default), und das Netz hat keinen Ausgang' '[ "$AUS" = "$NETZ " ] && [ "$(docker network inspect -f "{{.Internal}}" "$NETZ")" = true ]'
AUS="$(I '{{json .HostConfig.PortBindings}}')"
ok "keine Ports zum Server veröffentlicht" '[ "$AUS" = "{}" ] || [ "$AUS" = "null" ]'

# ── Zur Laufzeit ──
AUS="$(docker exec "$C" sh -c 'for p in /proc/[0-9]*; do stat -c %u "$p"; done | sort -u | tr "\n" " "; grep -E "^(CapPrm|CapEff|CapBnd|CapAmb):" /proc/1/status | tr -s "\t " " " | tr "\n" " "; grep -E "^(NoNewPrivs|Seccomp):" /proc/1/status | tr -s "\t " " " | tr "\n" " "')"
ok "alle Prozesse als www-data (auch der Apache-Hauptprozess), keinerlei Sonderrechte, seccomp aktiv" \
  'echo "$AUS" | grep -q "^33 CapPrm: 0000000000000000 CapEff: 0000000000000000 CapBnd: 0000000000000000 CapAmb: 0000000000000000 NoNewPrivs: 1 Seccomp: 2"'
AUS="$(docker exec "$C" sh -c 'touch /etc/probe 2>&1; touch /var/www/html/probe 2>&1; touch /usr/local/bin/probe 2>&1' || true)"
ok "Dateisystem und Anwendung nur lesbar" '[ "$(echo "$AUS" | grep -c "Read-only file system")" = 3 ]'
AUS="$(docker exec "$C" sh -c 'for d in /tmp /run; do printf "#!/bin/sh\necho lief\n" > $d/p.sh && chmod +x $d/p.sh && $d/p.sh 2>&1; done' || true)"
ok "in /tmp und /run lässt sich nichts ausführen" '! echo "$AUS" | grep -q lief && [ "$(echo "$AUS" | grep -c "Permission denied")" = 2 ]'
AUS="$(docker exec "$C" sh -c 'touch /var/www/html/data/.probe && echo daten-ok' 2>&1 || true)"
ok "Datenordner bleibt beschreibbar" 'echo "$AUS" | grep -q daten-ok'
AUS="$(docker exec "$C" sh -c 'curl -s -m 5 -o /dev/null https://example.com && echo AUSGANG; curl -s -m 5 -o /dev/null http://1.1.1.1 && echo AUSGANG; getent hosts example.com && echo DNS; true' 2>&1)"
ok "kein Ausgang ins Internet (weder Name noch Adresse), kein DNS nach außen" '! echo "$AUS" | grep -q -E "AUSGANG|DNS"'
AUS="$(docker exec "$C" sh -c 'getent hosts app-mitarbeiter keycloak postausgang && echo ERREICHBAR; true' 2>&1)"
ok "Mitarbeiterseite, Keycloak und Postausgang aus dem Kundencontainer nicht auffindbar" '! echo "$AUS" | grep -q ERREICHBAR'
AUS="$(docker exec "$C" php -m | sort | tr "\n" " ")"; export BASIS_M; BASIS_M="$(docker run --rm "$BILD" php -m | sort | tr "\n" " ")"
ok "PHP-Erweiterungen des Images unverändert geladen (opcache, sodium …)" '[ "$AUS" = "$BASIS_M" ] && echo "$AUS" | grep -q sodium'

# ── Relais der Datenleck-Prüfung (einziger Weg nach außen) ──
c() { klient curl -s -o /dev/null -w '%{http_code}' "$@"; }
AUS="$(c http://caddy:8081/range/zzzzz) $(c http://caddy:8081/range/21BD) $(c http://caddy:8081/etwas) $(c -X POST http://caddy:8081/range/21BD1) $(c 'http://caddy:8081/range/21BD1/../../x')"
ok "Relais: andere Pfade, falsches Format und andere Methoden 404" '[ "$AUS" = "404 404 404 404 404" ]'
if docker run --rm --network "$P-aussen" "$BILD" curl -fsS -m 10 -o /dev/null https://api.pwnedpasswords.com/range/21BD1 2>/dev/null; then
  AUS="$(docker exec "$C" sh -c 'curl -s -m 15 http://caddy:8081/range/21BD1 | head -3')"
  ok "Relais: Kundencontainer erreicht api.pwnedpasswords.com (nur über Caddy)" 'echo "$AUS" | grep -q -E "^[0-9A-F]{35}:[0-9]+"'
  PWNED_ERWARTET=ok
else
  echo "SKIP Relais zu api.pwnedpasswords.com: dieses Netz erlaubt keinen Abruf (in der CI geprüft)"
  PWNED_ERWARTET=
fi

# ── PHP und Apache in der Kundenseite ──
h() { klient curl -s -H 'Host: angebot-stafl.de' "$@"; }
AUS="$(h http://app/kunde-haertung-probe.php)"
ok "PHP: Programme starten und Mails direkt unmöglich (exec, proc_open, mail …)" \
  'echo "$AUS" | grep -q "\"exec\":false,\"proc_open\":false,\"mail\":false" && echo "$AUS" | grep -q "\"disable\":\"exec,shell_exec,system,passthru,proc_open,popen"'
ok "PHP: Dateien nur unter der Anwendung und /tmp (open_basedir), /etc/passwd nicht lesbar" \
  'echo "$AUS" | grep -q "\"open_basedir\":\"\\\\/var\\\\/www\\\\/html:\\\\/tmp\",\"etc_passwd\":false"'
# ini_get liefert für „Off“ einen leeren Text (ohne die Datei wären file_uploads, expose_php und display_errors „1“)
ok "PHP: keine Uploads, Version verborgen, Fehler nicht im Browser, keine fremden Adressen als Code" \
  'echo "$AUS" | grep -q "\"uploads\":\"\",\"expose\":\"\",\"display\":\"\",\"url_include\":\"\""'
ok "PHP: Datenleck-Prüfung zeigt auf das Relais${PWNED_ERWARTET:+ und bekommt Antwort}" \
  'echo "$AUS" | grep -q "\"pwned_url\":\"http:\\\\/\\\\/caddy:8081\\\\/range\\\\/21BD1\"" && { [ -z "$PWNED_ERWARTET" ] || echo "$AUS" | grep -q "\"pwned\":\"ok\""; }'
AUS="$(h -D - -o /dev/null http://app/ | tr -d '\r')"
ok "Startseite 200, Apache ohne Version, kein X-Powered-By" 'echo "$AUS" | grep -q "^HTTP/1.1 200" && echo "$AUS" | grep -qx "Server: Apache" && ! echo "$AUS" | grep -qi "^X-Powered-By"'
AUS="$(h -o /dev/null -w '%{http_code}' -X TRACE http://app/)"
ok "TRACE abgelehnt (405)" '[ "$AUS" = 405 ]'
AUS="$(h 'http://app/api/?action=status')"
ok "Schnittstelle: Status ok" 'echo "$AUS" | grep -q "\"ok\":true"'
AUS="$(h -o /dev/null -w '%{http_code}' 'http://app/api/?action=offer')"
ok "Schnittstelle: Angebot 200" '[ "$AUS" = 200 ]'
touch "$T/marke"; sleep 1
AUS="$(klient sh -c '
  J=/tmp/j; curl -s -c $J -b $J -H "Host: angebot-stafl.de" "http://app/api/?action=kunde_status" > /tmp/s
  CSRF=$(sed -n "s/.*\"csrf\":\"\([^\"]*\)\".*/\1/p" /tmp/s)
  curl -s -c $J -b $J -o /tmp/a -w "%{http_code}" -H "Host: angebot-stafl.de" -H "Content-Type: application/json" -H "X-CSRF-Token: $CSRF" \
    -d "{\"username\":\"gibt-es-nicht\",\"password\":\"Falsches-Passwort-1\"}" "http://app/api/?action=kunde_login"; echo; head -c 300 /tmp/a; echo; grep -c csrf /tmp/s')"
ok "Kundenanmeldung (Fehlversuch): Sitzung, Prüfung und Antwort ohne Serverfehler" 'echo "$AUS" | head -1 | grep -q -E "^4[0-9][0-9]$" && echo "$AUS" | sed -n 2p | grep -q "\"error\""'
AUS="$(find "$T/daten" -type f -newer "$T/marke" | head -5)"
ok "Fehlversuch im Datenordner festgehalten (Kundenseite schreibt dort)" '[ -n "$AUS" ]'
AUS="$(docker logs "$C" 2>&1)"
ok "Protokoll ohne Rechte-, PHP- oder Startfehler" '! echo "$AUS" | grep -i -E "permission denied|open_basedir|php (fatal|warning|parse)|AH00(015|072|076|111)|could not (bind|open)|failed"'
echo "kundencontainer: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
