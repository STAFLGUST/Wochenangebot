#!/usr/bin/env bash
# Prüft das Anwendungs-Image (deploy/image/Dockerfile) gegen das bisherige Grundimage – lokal mit Docker und in der CI.
#   bash deploy/image/pruefen.sh            # baut stafl-app:pruefung und vergleicht
# Erwartung: gleiche geladene Apache-Module, gleiche PHP-Erweiterungen, gleiche Antworten der Anwendung (Startseite,
# Schnittstelle, Sicherheitskopfzeilen); mod_auth_openidc ist vorhanden, aber nicht geladen.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BASIS="$(sed -n 's/^FROM \(php:8\.3-apache@sha256:[0-9a-f]*\).*/\1/p' "$REPO/deploy/image/Dockerfile")"
BILD=stafl-app:pruefung
FEHLER=0
ok() { echo "PASS $1"; }
nein() { echo "FAIL $1${2:+  $2}"; FEHLER=1; }

docker build -q -t "$BILD" "$REPO/deploy/image" >/dev/null
docker pull -q "$BASIS" >/dev/null

mods() { docker run --rm "$1" apache2ctl -M 2>/dev/null | sort; }
[ "$(mods "$BASIS")" = "$(mods "$BILD")" ] && ok "gleiche geladene Apache-Module wie das Grundimage" || nein "Apache-Module weichen ab" "$(diff <(mods "$BASIS") <(mods "$BILD") | tr '\n' ' ')"
mods "$BILD" | grep -q auth_openidc && nein "mod_auth_openidc darf ohne Konfiguration nicht geladen sein" || ok "mod_auth_openidc nicht geladen"
docker run --rm "$BILD" test -f /usr/lib/apache2/modules/mod_auth_openidc.so && ok "mod_auth_openidc installiert" || nein "mod_auth_openidc fehlt"
docker run --rm "$BILD" sh -c 'apache2ctl -t -D DUMMY -C "LoadModule auth_openidc_module /usr/lib/apache2/modules/mod_auth_openidc.so" 2>&1' | grep -q "Syntax OK" \
  && ok "mod_auth_openidc ladbar" || nein "mod_auth_openidc lässt sich nicht laden"
pexts() { docker run --rm "$1" php -m | sort; }
[ "$(pexts "$BASIS")" = "$(pexts "$BILD")" ] && ok "gleiche PHP-Erweiterungen" || nein "PHP-Erweiterungen weichen ab"
VERSION="$(docker run --rm "$BILD" dpkg-query -W -f '${Version}' libapache2-mod-auth-openidc)"
echo "Info: libapache2-mod-auth-openidc $VERSION"

# Anwendung in beiden Images mit Testdaten starten und Antworten vergleichen
ARBEIT="$(mktemp -d)"; trap 'docker rm -f wa-basis wa-bild >/dev/null 2>&1; rm -rf "$ARBEIT"' EXIT
for name in basis bild; do
  mkdir -p "$ARBEIT/$name"; cp -r "$REPO/tests/fixtures/data-seed" "$ARBEIT/$name/data"; chmod -R a+rwX "$ARBEIT/$name/data"
done
docker run -d --name wa-basis -p 127.0.0.1:18081:80 -v "$REPO/app:/var/www/html:ro" -v "$ARBEIT/basis/data:/var/www/html/data" "$BASIS" >/dev/null
docker run -d --name wa-bild -p 127.0.0.1:18082:80 -v "$REPO/app:/var/www/html:ro" -v "$ARBEIT/bild/data:/var/www/html/data" "$BILD" >/dev/null
for p in 18081 18082; do for _ in $(seq 1 30); do curl -fsS -o /dev/null "http://127.0.0.1:$p/" 2>/dev/null && break; sleep 1; done; done
antwort() { curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$1$2"; }
for pfad in / /admin/ "/api/?action=status" "/api/?action=kunde_status" "/api/?action=gibt_es_nicht" /data/nutzer.php /wp-login.php; do
  a="$(antwort 18081 "$pfad")"; b="$(antwort 18082 "$pfad")"
  [ "$a" = "$b" ] && ok "gleiche Antwort $pfad ($a)" || nein "Antwort $pfad weicht ab" "Grundimage $a, neues Image $b"
done
kopf() { curl -sI "http://127.0.0.1:$1/" | grep -iE '^(content-security-policy|x-frame-options|x-content-type-options|referrer-policy|permissions-policy|cross-origin-resource-policy):' | tr -d '\r' | sort; }
# (Im Betrieb setzt Caddy die Sicherheitskopfzeilen; hier zählt nur, dass sich das Image nicht anders verhält.)
[ "$(kopf 18081)" = "$(kopf 18082)" ] && ok "gleiche Sicherheitskopfzeilen ($(kopf 18082 | wc -l) vom Webserver)" || nein "Sicherheitskopfzeilen weichen ab"
code="$(curl -s -o /dev/null -w '%{http_code}' -H 'Sec-Fetch-Site: cross-site' 'http://127.0.0.1:18082/api/?action=kunde_status')"
[ "$code" = 403 ] && ok "Herkunftsprüfung wirkt im neuen Image (403)" || nein "Herkunftsprüfung" "$code"
exit $FEHLER
