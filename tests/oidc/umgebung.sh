#!/usr/bin/env bash
# Testumgebung „Anmeldung über Keycloak“ (Roadmap 7b, ADR-003) – nur CI und lokal, nie auf dem Server (GR-111).
#   bash tests/oidc/umgebung.sh start   # PostgreSQL, Keycloak (Realm „mitarbeiter“), Caddy (TLS), Apache + mod_auth_openidc
#   python3 tests/oidc/test_oidc.py      # Prüfungen (Browser und HTTP)
#   bash tests/oidc/umgebung.sh stop
# Voraussetzungen (Ubuntu 24.04, wie in der CI): apache2, libapache2-mod-auth-openidc, libapache2-mod-php8.3, postgresql,
# Java 21; Keycloak und Caddy werden mit fester Version und Prüfsumme heruntergeladen. Hosts *.stafl.test → 127.0.0.1.
# Geheimnisse (Client-Geheimnisse, Schlüssel, Datenbank- und Verwaltungspasswort) entstehen bei jedem Start neu und
# liegen nur im Arbeitsordner (Datei geheim.env, nur für den Besitzer lesbar).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HIER="$REPO/tests/oidc"
export OIDC_WORK="${OIDC_WORK:-$REPO/tests/.arbeit/oidc}"
LADEN="${OIDC_DOWNLOADS:-$REPO/tests/.arbeit/downloads}"
export OIDC_PORT=8443 OIDC_HTTP_PORT="${OIDC_HTTP_PORT:-8081}" KC_PORT="${KC_PORT:-8180}" KC_MGMT_PORT="${KC_MGMT_PORT:-9180}"
export APACHE_PORT="${APACHE_PORT:-8280}" PG_PORT="${PG_PORT:-5433}"

KC_VERSION=26.7.5
KC_SHA256=87d680d13cf4600d232ca0433a2553c57ebf03e56f7718fc0d03a1a8705497c8
CADDY_VERSION=2.10.2
CADDY_SHA512=747df7ee74de188485157a383633a1a963fd9233b71fbb4a69ddcbcc589ce4e2cc82dacf5dbbe136cb51d17e14c59daeb5d9bc92487610b0f3b93680b2646546
HOSTS="login.stafl.test dashboard.stafl.test angebot.stafl.test legacy.stafl.test"
# Testhosts nie über einen Proxy (lokal und in der CI)
export no_proxy="${no_proxy:+$no_proxy,}.stafl.test" NO_PROXY="${NO_PROXY:+$NO_PROXY,}.stafl.test"

ALS_ROOT=0; [ "$(id -u)" = 0 ] && ALS_ROOT=1
als() { # Befehl als Benutzer $1 (nur wenn als root gestartet – PostgreSQL und Apache laufen nie als root)
  local wer="$1"; shift
  if [ "$ALS_ROOT" = 1 ]; then runuser -u "$wer" -- "$@"; else "$@"; fi
}
warte() { # warte <Beschreibung> <Sekunden> <Befehl…>
  local was="$1" n="$2"; shift 2
  for _ in $(seq 1 "$n"); do if "$@" >/dev/null 2>&1; then return 0; fi; sleep 1; done
  echo "Zeitüberschreitung: $was" >&2; return 1
}
zufall() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40; }

laden() { # laden <URL> <Datei> <Algorithmus> <Prüfsumme>
  mkdir -p "$LADEN"
  if [ ! -f "$LADEN/$2" ]; then curl -fsSL --retry 3 -o "$LADEN/$2.teil" "$1"; mv "$LADEN/$2.teil" "$LADEN/$2"; fi
  echo "$4  $LADEN/$2" | "${3}sum" -c --quiet - || { echo "Prüfsumme falsch: $2" >&2; rm -f "$LADEN/$2"; exit 1; }
}

hosts_eintragen() {
  for h in $HOSTS; do
    grep -qE "^127\.0\.0\.1[[:space:]].*\b$h\b" /etc/hosts && continue
    if [ "$ALS_ROOT" = 1 ]; then echo "127.0.0.1 $h" >> /etc/hosts; else echo "127.0.0.1 $h" | sudo tee -a /etc/hosts >/dev/null; fi
  done
}

pg_bin() { ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1; }

start() {
  stop >/dev/null 2>&1 || true
  rm -rf "$OIDC_WORK"; mkdir -p "$OIDC_WORK"/{apache,sessions,pgsock}; chmod 700 "$OIDC_WORK"
  hosts_eintragen
  umask 077
  cat > "$OIDC_WORK/geheim.env" <<EOF
OIDC_CRYPTO_DASHBOARD=$(zufall)
OIDC_CRYPTO_ANGEBOT=$(zufall)
OIDC_CRYPTO_LEGACY=$(zufall)
OIDC_SECRET_DASHBOARD=$(zufall)
OIDC_SECRET_ANGEBOT=$(zufall)
KC_DB_PASSWORD=$(zufall)
KC_ADMIN_PASSWORD=$(zufall)
EOF
  umask 022
  set -a; . "$OIDC_WORK/geheim.env"; set +a

  # ── PostgreSQL: eigene Instanz nur für Keycloak (eigene Datenbank und Rolle, getrennt von Geschäftsdaten – ADR-003) ──
  local pg; pg="$(pg_bin)"
  mkdir -p "$OIDC_WORK/pg"
  if [ "$ALS_ROOT" = 1 ]; then chown postgres "$OIDC_WORK/pg" "$OIDC_WORK/pgsock"; chmod 711 "$OIDC_WORK"; fi
  printf '%s\n' "$KC_DB_PASSWORD" > "$OIDC_WORK/pgsock/pw"; [ "$ALS_ROOT" = 1 ] && chown postgres "$OIDC_WORK/pgsock/pw"
  als postgres "$pg/initdb" -D "$OIDC_WORK/pg" -A scram-sha-256 -U postgres --pwfile="$OIDC_WORK/pgsock/pw" >/dev/null
  rm -f "$OIDC_WORK/pgsock/pw"
  als postgres "$pg/pg_ctl" -D "$OIDC_WORK/pg" -l "$OIDC_WORK/pg/log" -o "-p $PG_PORT -k $OIDC_WORK/pgsock -c listen_addresses=127.0.0.1" -w start >/dev/null
  PGPASSWORD="$KC_DB_PASSWORD" psql -h 127.0.0.1 -p "$PG_PORT" -U postgres -q -v ON_ERROR_STOP=1 \
    -c "CREATE ROLE keycloak LOGIN PASSWORD '$KC_DB_PASSWORD'" -c "CREATE DATABASE keycloak OWNER keycloak" >/dev/null

  # ── Keycloak (feste Version, Prüfsumme) mit Realm „mitarbeiter“ ──
  laden "https://github.com/keycloak/keycloak/releases/download/$KC_VERSION/keycloak-$KC_VERSION.tar.gz" "keycloak-$KC_VERSION.tar.gz" sha256 "$KC_SHA256"
  tar xzf "$LADEN/keycloak-$KC_VERSION.tar.gz" -C "$OIDC_WORK"
  local kc="$OIDC_WORK/keycloak-$KC_VERSION"
  mkdir -p "$kc/data/import"
  sed -e "s/@GEHEIM_DASHBOARD@/$OIDC_SECRET_DASHBOARD/" -e "s/@GEHEIM_ANGEBOT@/$OIDC_SECRET_ANGEBOT/" \
    "$HIER/realm-mitarbeiter.json" > "$kc/data/import/realm-mitarbeiter.json"
  export KC_DB=postgres KC_DB_URL="jdbc:postgresql://127.0.0.1:$PG_PORT/keycloak" KC_DB_USERNAME=keycloak
  export KC_HOSTNAME="https://login.stafl.test:$OIDC_PORT" KC_HTTP_ENABLED=true KC_HTTP_HOST=127.0.0.1 KC_HTTP_PORT="$KC_PORT"
  export KC_HTTP_MANAGEMENT_PORT="$KC_MGMT_PORT" KC_PROXY_HEADERS=xforwarded KC_HEALTH_ENABLED=true
  export KC_BOOTSTRAP_ADMIN_USERNAME=verwaltung-ci KC_BOOTSTRAP_ADMIN_PASSWORD="$KC_ADMIN_PASSWORD"
  export JAVA_OPTS_KC_HEAP="-Xms256m -Xmx768m"
  # Back-Channel-Logout an die Anwendungen: nur mit unserer Test-CA und direkt (Proxy-Vorgaben der Umgebung entfernt)
  export KC_TRUSTSTORE_PATHS="$OIDC_WORK/caddy/pki/authorities/local/root.crt"

  # ── Anwendung: Kopie von app/ und dashboard/, Testdaten aus tests/fixtures (GR-007) ──
  cp -r "$REPO/app" "$OIDC_WORK/app"; cp -r "$REPO/dashboard" "$OIDC_WORK/app/dashboard"
  rm -rf "$OIDC_WORK/app/data"; cp -r "$REPO/tests/fixtures/data-seed" "$OIDC_WORK/app/data"
  php -r 'echo "<?php http_response_code(404); exit; ?>\n" . json_encode(["hash" => password_hash($argv[1], PASSWORD_DEFAULT), "created" => "2026-10-01T00:00:00Z"]);' \
    "Sicheres-Passwort-1" > "$OIDC_WORK/app/data/admin.php"
  if [ "$ALS_ROOT" = 1 ]; then chown -R www-data "$OIDC_WORK/app/data" "$OIDC_WORK/sessions" "$OIDC_WORK/apache"; fi

  # ── Caddy (TLS wie in der Produktion, Test-CA) ──
  laden "https://github.com/caddyserver/caddy/releases/download/v$CADDY_VERSION/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" "caddy-$CADDY_VERSION.tar.gz" sha512 "$CADDY_SHA512"
  mkdir -p "$OIDC_WORK/bin"; tar xzf "$LADEN/caddy-$CADDY_VERSION.tar.gz" -C "$OIDC_WORK/bin" caddy
  nohup "$OIDC_WORK/bin/caddy" run --config "$HIER/Caddyfile" --adapter caddyfile >"$OIDC_WORK/caddy.log" 2>&1 &
  echo $! > "$OIDC_WORK/caddy.pid"
  warte "Test-CA von Caddy" 30 test -f "$OIDC_WORK/caddy/pki/authorities/local/root.crt"
  chmod 755 "$OIDC_WORK/caddy" "$OIDC_WORK/caddy/pki" "$OIDC_WORK/caddy/pki/authorities" "$OIDC_WORK/caddy/pki/authorities/local"
  chmod 644 "$OIDC_WORK/caddy/pki/authorities/local/root.crt"

  "$kc/bin/kc.sh" build --db=postgres --health-enabled=true >"$OIDC_WORK/keycloak-build.log" 2>&1
  nohup env -u JAVA_TOOL_OPTIONS -u https_proxy -u HTTPS_PROXY -u http_proxy -u HTTP_PROXY "$kc/bin/kc.sh" start --optimized --import-realm >"$OIDC_WORK/keycloak.log" 2>&1 &
  echo $! > "$OIDC_WORK/keycloak.pid"

  warte "Keycloak bereit" 240 curl -fsS "http://127.0.0.1:$KC_MGMT_PORT/health/ready"
  warte "Realm über Caddy erreichbar" 60 curl -fsS --cacert "$OIDC_WORK/caddy/pki/authorities/local/root.crt" \
    "https://login.stafl.test:$OIDC_PORT/realms/mitarbeiter/.well-known/openid-configuration"

  # ── Apache mit mod_auth_openidc (nie als root) ──
  local def=(); [ "$ALS_ROOT" = 1 ] && def=(-DALS_ROOT)
  apache2 -f "$HIER/apache.conf" "${def[@]}" -t >/dev/null 2>&1 || apache2 -f "$HIER/apache.conf" "${def[@]}" -t
  apache2 -f "$HIER/apache.conf" "${def[@]}" -k start
  warte "Apache bereit" 30 curl -fsS -o /dev/null -H "Host: legacy.stafl.test" "http://127.0.0.1:$APACHE_PORT/api/?action=status"
  echo "Testumgebung läuft: https://dashboard.stafl.test:$OIDC_PORT/ · https://angebot.stafl.test:$OIDC_PORT/ · Arbeitsordner $OIDC_WORK"
}

stop() (   # eigene Subshell: Fehler beim Beenden brechen nichts ab
  set +e
  if [ -f "$OIDC_WORK/apache/httpd.pid" ]; then
    local def=(); [ "$ALS_ROOT" = 1 ] && def=(-DALS_ROOT)
    set -a; [ -f "$OIDC_WORK/geheim.env" ] && . "$OIDC_WORK/geheim.env"; set +a
    apache2 -f "$HIER/apache.conf" "${def[@]}" -k stop 2>/dev/null
  fi
  for p in caddy keycloak; do [ -f "$OIDC_WORK/$p.pid" ] && kill "$(cat "$OIDC_WORK/$p.pid")" 2>/dev/null; done
  [ -d "$OIDC_WORK/pg" ] && als postgres "$(pg_bin)/pg_ctl" -D "$OIDC_WORK/pg" -m fast stop >/dev/null 2>&1
  sleep 1
  exit 0
)

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  *) echo "Aufruf: $0 start|stop" >&2; exit 2 ;;
esac
