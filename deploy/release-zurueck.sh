#!/bin/sh
# Notfall: auf die Version vor dem letzten Release zurückgehen (Daten bleiben unverändert).
#   sh /opt/wochenangebot/deploy/release-zurueck.sh
# Der zurückgenommene Stand wird nicht erneut automatisch eingespielt; ein neuer Release ist dafür nötig.
#
# Container wie in freigabe-einspielen.sh: alle neu erstellen, wenn sich Caddyfile, docker-compose.yml oder die
# Ergänzungsdatei der Anmeldung zwischen den Ständen unterscheiden. Unterscheidet sich deploy/image/ und ist die
# Ergänzungsdatei über COMPOSE_FILE in .env aktiv, wird das beim Release gemerkte Image stafl-app:release-vorher wieder
# auf den aktiven Namen getaggt (fehlt es: aus dem Bauplan des vorherigen Stands bauen, bei Fehlschlag Abbruch ohne
# Codewechsel) und die App neu erstellt.
#
# Für Tests überschreibbar: WA_COMPOSE, WA_DOCKER
set -eu
cd "$(dirname "$0")/.."
COMPOSE=${WA_COMPOSE:-docker compose}
DOCKER=${WA_DOCKER:-docker}
envwert() { sed -n "s/^$1=//p" .env 2>/dev/null | head -1 | tr -d '"'"'"' '; }
ANMELDUNG_COMPOSE=deploy/anmeldung/docker-compose.anmeldung.yml
APP_VERSION=$(envwert STAFL_APP_VERSION)
APP_BILD="stafl-app:${APP_VERSION:-lokal}"   # Name wie in der Ergänzungsdatei: stafl-app:${STAFL_APP_VERSION:-lokal}
BILD_VORHER=stafl-app:release-vorher

VORHER=$(python3 -c "import json; t=open('daten/deployment.php').read(); print(json.loads(t[t.index(chr(10))+1:]).get('vorher',''))" 2>/dev/null || true)
printf '%s' "$VORHER" | grep -qE '^[0-9a-f]{40}$' || { echo "Kein vorheriger Stand bekannt."; exit 1; }
JETZT=$(git rev-parse HEAD)
[ "$VORHER" != "$JETZT" ] || { echo "Vorheriger Stand ist bereits aktiv."; exit 0; }
# Nach einem automatischen Rückfall steht der abgelehnte Release als „vorher“ im Status – nie dorthin wechseln
if [ "$VORHER" = "$(cat .release-abgelehnt 2>/dev/null)" ]; then
  echo "Der vorherige Stand $VORHER wurde abgelehnt bzw. automatisch zurückgenommen – kein Rückfall dorthin."
  exit 1
fi
if [ -f daten/.sqlite-active ] && ! git cat-file -e "$VORHER:app/api/storage.php" 2>/dev/null; then
  echo "SQLite aktiv: Zuerst deploy/datenbank-umschalten.sh rollback ausführen."
  exit 1
fi

# Anwendungs-Image: nur wenn sich deploy/image/ unterscheidet und die App dieses Image nutzt (COMPOSE_FILE)
BILD=0
if git diff --name-only "$JETZT" "$VORHER" | grep -q '^deploy/image/' && envwert COMPOSE_FILE | grep -qF "$ANMELDUNG_COMPOSE"; then
  BILD=1
  if $DOCKER image inspect "$BILD_VORHER" >/dev/null 2>&1; then
    $DOCKER tag "$BILD_VORHER" "$APP_BILD" \
      || { echo "Gemerktes Image $BILD_VORHER ließ sich nicht als $APP_BILD taggen – Rückfall abgebrochen, Code und Container unverändert."; exit 1; }
    echo "Gemerktes Image $BILD_VORHER wieder als $APP_BILD aktiv."
  else
    echo "Gemerktes Image $BILD_VORHER fehlt – baue das Image aus dem Bauplan des vorherigen Stands (kann einige Minuten dauern)."
    # Nur Bauplan und Compose-Dateien des vorherigen Stands auschecken; App-Code und laufende Container bleiben unverändert
    if rm -rf deploy/image && git checkout -q "$VORHER" -- deploy/image docker-compose.yml "$ANMELDUNG_COMPOSE" && $COMPOSE build app; then
      echo "Image aus dem vorherigen Stand gebaut."
    else
      git reset -q --hard "$JETZT"
      echo "Image-Bau fehlgeschlagen – Rückfall abgebrochen, Code und Container unverändert ($(git log -1 --format='%h %s'))."
      exit 1
    fi
  fi
fi

echo "$JETZT" > .release-abgelehnt
git reset -q --hard "$VORHER"
# Container-Konfiguration geändert: alle neu erstellen; nur das Image: nur die App (Keycloak und seine Datenbank laufen weiter)
if git diff --name-only "$JETZT" "$VORHER" | grep -qE '^(Caddyfile|docker-compose\.yml|deploy/anmeldung/docker-compose\.anmeldung\.yml)$'; then $COMPOSE up -d --force-recreate
elif [ "$BILD" = 1 ]; then $COMPOSE up -d --force-recreate app; fi
echo "Zurückgesetzt auf $(git log -1 --format='%h %s')"
