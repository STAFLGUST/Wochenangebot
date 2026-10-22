#!/usr/bin/env bash
# Prüft die vorbereitete Betriebskonfiguration der zentralen Anmeldung (deploy/anmeldung) – lokal mit Docker und in der CI.
# Startet nichts auf einem Server. Prüft:
#   1. Realm für den Betrieb aktuell (aus dem geprüften Test-Realm erzeugt, ohne Testnutzer, Geheimnisse nur Platzhalter)
#   2. docker compose mit Ergänzungsdatei gültig; alle neuen Images fest über Digest
#   3. Anwendungs-Image mit apache-oidc.conf: Konfiguration gültig; angebot-stafl.de (Standard-Host) verhält sich
#      unverändert; die neuen Hosts liefern ohne Anmeldung nichts aus der Anwendung aus
#   3b. Keycloak startet wirklich – mit Start-Konto und nach der Einrichtung ohne (Neustart)
#   4. Caddyfile (mit den Anmelde-Hosts) gültig; deren Ziele gibt es nur mit der Ergänzungsdatei
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HIER="$REPO/deploy/anmeldung"
FEHLER=0
ok() { echo "PASS $1"; }
nein() { echo "FAIL $1${2:+  $2}"; FEHLER=1; }

python3 "$REPO/werkzeuge/realm_produktion.py" --pruefen >/dev/null && ok "Realm für den Betrieb aktuell" || nein "Realm veraltet (werkzeuge/realm_produktion.py)"
python3 - "$HIER/realm-mitarbeiter.json" <<'PY' && ok "Realm: keine Testnutzer, keine Testadressen, Geheimnisse nur Platzhalter" || nein "Realm enthält Testdaten oder Geheimnisse"
import json, sys
t = open(sys.argv[1], encoding='utf-8').read(); r = json.loads(t)
assert 'users' not in r and 'stafl.test' not in t and 'nur-fuer-tests' not in t
assert all(c['secret'].startswith('@GEHEIM_') for c in r['clients'])
host = {'dashboard': 'dashboard-stafl.de', 'angebot': 'angebot.dashboard-stafl.de', 'verwaltung': 'verwaltung.dashboard-stafl.de'}
assert sorted(c['clientId'] for c in r['clients']) == sorted(host)
assert all(c['redirectUris'] == [f"https://{host[c['clientId']]}/oidc/callback"] for c in r['clients'])
assert all(c['secret'] == f"@GEHEIM_{c['clientId'].upper()}@" for c in r['clients'])
PY

# ── 2. Compose ──
ENV="$(mktemp)"; trap 'rm -f "$ENV"; docker rm -f stafl-pruefung >/dev/null 2>&1 || true' EXIT
cat > "$ENV" <<'EOF'
DOMAIN=angebot-stafl.de
OIDC_SECRET_DASHBOARD=pruefung
OIDC_SECRET_ANGEBOT=pruefung
OIDC_CRYPTO_DASHBOARD=pruefung-a
OIDC_CRYPTO_ANGEBOT=pruefung-b
KC_DB_PASSWORD=pruefung
EOF
if docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config -q 2>/tmp/compose-fehler.txt; then ok "docker compose mit Ergänzungsdatei gültig"; else nein "docker compose" "$(cat /tmp/compose-fehler.txt)"; fi
ohne="$(grep -E '^\s+image:' "$HIER/docker-compose.anmeldung.yml" | grep -v '@sha256:' | grep -v 'stafl-app:' || true)"
[ -z "$ohne" ] && ok "neue Images fest über Digest" || nein "Images ohne Digest" "$ohne"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); kc=d['services']['keycloak']; db=d['services']['keycloak-db']; \
assert all(p.get('host_ip')=='127.0.0.1' for p in kc.get('ports',[])); assert not db.get('ports'); assert list(db['networks'])==['anmeldung']; \
assert d['networks']['anmeldung'].get('internal') is True" \
  && ok "Keycloak nur lokal erreichbar, Datenbank nur im internen Netz" || nein "Netz/Ports von Keycloak bzw. Datenbank"
# Ziele der Anmelde-Hosts in Caddy (app-mitarbeiter, keycloak) nur mit der Ergänzungsdatei – ohne sie: 502 statt App ohne Anmeldung
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'app-mitarbeiter' in (d['services']['app']['networks']['default'] or {}).get('aliases', [])" \
  && docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); s=d['services']; assert 'keycloak' not in s; assert all('app-mitarbeiter' not in json.dumps(v) for v in s.values())" \
  && ok "Ziele app-mitarbeiter und keycloak nur mit der Ergänzungsdatei" || nein "Netzwerkname app-mitarbeiter bzw. keycloak"
# Release vor dem Konsolenschritt für die Verwaltung (Werte fehlen in .env): Anwendung startet trotzdem, Schlüssel nie leer
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app']['environment']; assert e['OIDC_CRYPTO_VERWALTUNG']=='pruefung-b' and e['OIDC_SECRET_VERWALTUNG']" \
  && ok "Verwaltung: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "Verwaltung ohne Werte in .env"
printf 'OIDC_SECRET_VERWALTUNG=pruefung-v\nOIDC_CRYPTO_VERWALTUNG=pruefung-c\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app']['environment']; assert e['OIDC_CRYPTO_VERWALTUNG']=='pruefung-c' and e['OIDC_SECRET_VERWALTUNG']=='pruefung-v'" \
  && ok "Verwaltung: eigene Werte aus .env" || nein "Verwaltung: eigene Werte aus .env"

# ── 3. Anwendungs-Image mit der Betriebskonfiguration ──
docker build -q -t stafl-app:pruefung "$REPO/deploy/image" >/dev/null
DATEN="$(mktemp -d)"; cp -r "$REPO/tests/fixtures/data-seed/." "$DATEN/"; chmod -R a+rwX "$DATEN"
docker run -d --name stafl-pruefung -p 127.0.0.1:18090:80 \
  -e OIDC_ISSUER=https://login.dashboard-stafl.de/realms/mitarbeiter -e OIDC_SECRET_DASHBOARD=x -e OIDC_SECRET_ANGEBOT=x \
  -e OIDC_CRYPTO_DASHBOARD=pruefung-a -e OIDC_CRYPTO_ANGEBOT=pruefung-b -e OIDC_SECRET_VERWALTUNG=x -e OIDC_CRYPTO_VERWALTUNG=pruefung-c \
  -v "$REPO/app:/var/www/html:ro" -v "$DATEN:/var/www/html/data" -v "$REPO/dashboard:/var/www/dashboard:ro" \
  -v "$HIER/apache-oidc.conf:/etc/apache2/sites-enabled/zz-stafl-oidc.conf:ro" stafl-app:pruefung >/dev/null
for _ in $(seq 1 30); do curl -fsS -o /dev/null http://127.0.0.1:18090/ 2>/dev/null && break; sleep 1; done
docker exec stafl-pruefung apache2ctl -t 2>&1 | grep -q "Syntax OK" && ok "Apache-Konfiguration gültig" || nein "Apache-Konfiguration" "$(docker exec stafl-pruefung apache2ctl -t 2>&1 | tail -3)"
docker exec stafl-pruefung apache2ctl -M 2>/dev/null | grep -q auth_openidc && ok "mod_auth_openidc geladen" || nein "mod_auth_openidc nicht geladen"
code() { curl -s -o /dev/null -w '%{http_code}' -H "Host: $1" -H 'X-Forwarded-Proto: https' "${@:3}" "http://127.0.0.1:18090$2"; }
[ "$(code angebot-stafl.de /)" = 200 ] && ok "angebot-stafl.de: Startseite wie bisher" || nein "angebot-stafl.de Startseite" "$(code angebot-stafl.de /)"
[ "$(code angebot-stafl.de '/api/?action=kunde_status')" = 200 ] && ok "angebot-stafl.de: Schnittstelle wie bisher" || nein "angebot-stafl.de Schnittstelle"
antwort="$(curl -s -H 'Host: angebot-stafl.de' -H 'Content-Type: application/json' -d '{"username":"x","password":"y"}' 'http://127.0.0.1:18090/api/?action=kunde_login')"
echo "$antwort" | grep -q "nicht korrekt" && ok "angebot-stafl.de: eigene Anmeldung unverändert (keine Keycloak-Sperre)" || nein "angebot-stafl.de Anmeldung" "$antwort"
[ "$(code angebot-stafl.de /dashboard/)" = 404 ] && ok "angebot-stafl.de: kein Dashboard" || nein "Dashboard auf angebot-stafl.de" "$(code angebot-stafl.de /dashboard/)"
[ "$(code unbekannt.example /)" = 200 ] && ok "unbekannter Host fällt auf den bisherigen Standard zurück" || nein "Standard-Host"
for h in dashboard-stafl.de angebot.dashboard-stafl.de verwaltung.dashboard-stafl.de; do
  c="$(code "$h" '/api/?action=status')"; [ "$c" = 401 ] && ok "$h: Schnittstelle ohne Anmeldung 401" || nein "$h Schnittstelle ohne Anmeldung" "$c"
  c="$(code "$h" '/api/?action=login' -H 'Content-Type: application/json' -d '{}')"; [ "$c" = 401 ] && ok "$h: eigene Anmeldung nicht erreichbar" || nein "$h Anmeldung" "$c"
  c="$(code "$h" /admin/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "$h: Eingabebereich nur über Keycloak ($c, ohne Keycloak hier nicht erreichbar)";; *) nein "$h Eingabebereich" "$c";; esac
  c="$(code "$h" /dashboard/abgemeldet.html)"; [ "$c" = 200 ] && ok "$h: Abmeldeseite öffentlich" || nein "$h Abmeldeseite" "$c"
done
docker logs stafl-pruefung 2>&1 | grep -iE "AH0|error" | grep -viE "metadata|oidc_provider_static_config|oidc_util_http|curl" | head -3 | sed 's/^/Info: /' || true

# ── 3b. Keycloak wirklich starten (wie auf dem Server): mit Start-Konto, dann ohne (nach konten.sh verwaltung) neu ──
KCP="$(mktemp -d)"; KCPROJ=stafl-kcpruefung
kc_ende() { (cd "$KCP" && docker compose -p "$KCPROJ" down -v >/dev/null 2>&1); rm -rf "$KCP"; }
mkdir -p "$KCP/deploy/anmeldung"
cp "$REPO/docker-compose.yml" "$KCP/"; cp "$HIER/docker-compose.anmeldung.yml" "$HIER/realm-mitarbeiter.json" "$HIER/einrichten.sh" "$KCP/deploy/anmeldung/"
printf 'DOMAIN=angebot-stafl.de\nCOMPOSE_FILE=docker-compose.yml:deploy/anmeldung/docker-compose.anmeldung.yml\n' > "$KCP/.env"
(cd "$KCP" && sh deploy/anmeldung/einrichten.sh >/dev/null)
# einrichten.sh übergibt den Realm-Import nur als root an den Keycloak-Benutzer (1000); ohne root (CI) diese Wegwerf-Kopie freigeben
[ "$(id -u)" = 0 ] || chmod -R a+rX "$KCP/daten-anmeldung/realm-import" "$KCP/daten-anmeldung/vault"
# bis 400 s: der erste Start (Datenbank anlegen, Indizes prüfen) dauert auf CI-Rechnern deutlich länger
kc_bereit() { for _ in $(seq 1 200); do curl -fsS -o /dev/null http://127.0.0.1:8180/realms/mitarbeiter/.well-known/openid-configuration 2>/dev/null && return 0; sleep 2; done; return 1; }
if (cd "$KCP" && docker compose -p "$KCPROJ" up -d keycloak-db keycloak >/dev/null 2>&1) && kc_bereit; then
  ok "Keycloak startet mit Start-Konto (Ersteinrichtung)"
  START_PW=$(sed -n 's/^KC_BOOTSTRAP_ADMIN_PASSWORD=//p' "$KCP/daten-anmeldung/einrichtung.env")
  curl -fsS -d grant_type=password -d client_id=admin-cli -d username=einrichtung --data-urlencode "password=$START_PW" \
    http://127.0.0.1:8180/realms/master/protocol/openid-connect/token 2>/dev/null | grep -q access_token \
    && ok "Start-Konto aus daten-anmeldung/einrichtung.env funktioniert" || nein "Start-Konto"
else
  nein "Keycloak startet nicht (Ersteinrichtung)" "$(cd "$KCP" && docker compose -p "$KCPROJ" logs --tail 15 keycloak 2>&1)"
fi
rm -f "$KCP/daten-anmeldung/einrichtung.env"   # wie nach konten.sh verwaltung
if (cd "$KCP" && docker compose -p "$KCPROJ" up -d --force-recreate keycloak >/dev/null 2>&1) && sleep 5 && kc_bereit \
  && [ -z "$(cd "$KCP" && docker compose -p "$KCPROJ" exec -T keycloak env | grep '^KC_BOOTSTRAP')" ]; then
  ok "Keycloak startet nach der Einrichtung ohne Start-Konto neu (keine leeren KC_BOOTSTRAP-Variablen)"
else
  nein "Keycloak startet nach der Einrichtung nicht neu" "$(cd "$KCP" && docker compose -p "$KCPROJ" logs --tail 15 keycloak 2>&1)"
fi
kc_ende

# ── 4. Caddy ──
if docker run --rm -e DOMAIN=angebot-stafl.de -v "$REPO/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/tmp/caddy-pruefung.txt 2>&1; then
  ok "Caddyfile mit den Anmelde-Hosts gültig"
else
  nein "Caddyfile" "$(tail -3 /tmp/caddy-pruefung.txt)"
fi
exit $FEHLER
