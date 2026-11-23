#!/bin/sh
# Notfall: auf die Version vor dem letzten Release zurückgehen (Daten bleiben unverändert).
#   sh /opt/wochenangebot/deploy/release-zurueck.sh
# Der zurückgenommene Stand wird nicht erneut automatisch eingespielt; ein neuer Release ist dafür nötig. Sperrt
# .release-abgelehnt schon einen neueren Release (automatisch zurückgenommen), bleibt diese Sperre stattdessen stehen.
#
# Container wie in freigabe-einspielen.sh: alle neu erstellen, wenn sich Caddyfile, docker-compose.yml oder die
# Ergänzungsdatei der Anmeldung zwischen den Ständen unterscheiden. Unterscheidet sich deploy/image/ und ist die
# Ergänzungsdatei über COMPOSE_FILE in .env aktiv, wird das beim Release gemerkte Image stafl-app:release-vorher wieder
# auf den aktiven Namen getaggt (fehlt es: aus dem Bauplan des vorherigen Stands bauen, bei Fehlschlag Abbruch ohne
# Codewechsel) und die App neu erstellt.
#
# Zwei Anwendungs-Container (ADR-007): Kundenseite „app“ und Mitarbeiter-Hosts „app-mitarbeiter“ aus demselben Image –
# anderes Image → beide neu erstellen, nur die Apache-Konfiguration der Anmeldung → nur app-mitarbeiter (ältere Stände: „app“).
#
# Danach Versionsnummern und Prüfliste aus dem zurückgeholten Commit (deploy/bereitstellen.py, falls dort vorhanden).
# Kein Rückfall (nichts geändert), wenn SQLite aktiv ist und der vorherige Stand nur Dateien kennt, oder wenn die Daten weiter
# getrennt sind, als der vorherige Stand kennt (erst deploy/daten-trennen.sh zusammenfuehren).
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

# Vorheriger Stand aus .release-vorher (schreibt nur freigabe-einspielen.sh als root). daten/deployment.php ist im
# Container beschreibbar und wird nur als Übergang gelesen (Releases vor dieser Datei), dann nur ein Vorgänger von HEAD.
JETZT=$(git rev-parse HEAD)
if [ -f .release-vorher ] && [ ! -L .release-vorher ]; then
  VORHER=$(head -n 1 .release-vorher)
else
  VORHER=$(python3 -c "import json; t=open('daten/deployment.php').read(); print(json.loads(t[t.index(chr(10))+1:]).get('vorher',''))" 2>/dev/null || true)
  if printf '%s' "$VORHER" | grep -qE '^[0-9a-f]{40}$' && [ "$VORHER" != "$JETZT" ]; then
    git merge-base --is-ancestor "$VORHER" "$JETZT" 2>/dev/null \
      || { echo "Vorheriger Stand $VORHER ist kein Vorgänger des aktiven Stands – kein Rückfall. Bitte von Hand prüfen."; exit 1; }
    echo "Hinweis: .release-vorher fehlt – vorheriger Stand aus daten/deployment.php ($VORHER), bitte vor dem Fortsetzen prüfen."
  fi
fi
printf '%s' "$VORHER" | grep -qE '^[0-9a-f]{40}$' || { echo "Kein vorheriger Stand bekannt."; exit 1; }
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
# Trennstufe (ADR-007): Sind die Daten weiter getrennt, als der vorherige Stand kennt, bräche dort jeder Speicherzugriff ab
# („Daten sind weiter getrennt“). Stufe der Daten: das höhere der beiden Kennzeichen; Stufe des Stands: DATEN_TRENNSTUFE,
# ältere Stände ohne die Konstante kennen höchstens Stufe 1 (Stufe 2a) bzw. keine Trennung
# Stufe eines Kennzeichens wie stufe_lesen() in deploy/daten_trennen.py: fehlt es 0, leer 1, sonst die Zahl (mindestens 1).
# Anderer Inhalt bricht ab – eine angenommene Stufe könnte den Rückfall auf einen Stand erlauben, der die Daten nicht kennt
trennstufe() {
  if [ ! -f "$1" ]; then echo 0; return 0; fi
  s=$(cat "$1") || return 1
  case $s in *[!0-9]*) return 1 ;; esac
  awk -v s="$s" 'BEGIN { print (s + 0 < 1) ? 1 : s + 0 }'
}
unlesbar() { echo "Kennzeichen $1 unlesbar – kein Rückfall, nichts geändert. Zustand prüfen: sh deploy/daten-trennen.sh status"; exit 1; }
DATENSTUFE=$(trennstufe daten/.daten-getrennt) || unlesbar daten/.daten-getrennt
INNEN=$(trennstufe daten-intern/.daten-intern) || unlesbar daten-intern/.daten-intern
if [ "$INNEN" -gt "$DATENSTUFE" ]; then DATENSTUFE=$INNEN; fi
ZIELSTUFE=$(git show "$VORHER:app/api/lib/datenbereiche-liste.php" 2>/dev/null | sed -n 's/^const DATEN_TRENNSTUFE = \([0-9][0-9]*\);.*/\1/p' | head -1)
if [ -z "$ZIELSTUFE" ]; then
  if git show "$VORHER:app/api/storage.php" 2>/dev/null | grep -q 'daten-getrennt'; then ZIELSTUFE=1; else ZIELSTUFE=0; fi
fi
if [ "$DATENSTUFE" -gt "$ZIELSTUFE" ]; then
  echo "Daten sind getrennt (Stufe $DATENSTUFE), der vorherige Stand $VORHER kennt nur Stufe $ZIELSTUFE – kein Rückfall, nichts geändert."
  echo "Zuerst sh deploy/daten-trennen.sh zusammenfuehren (Freigabe, Wartungsfenster), dann erneut sh deploy/release-zurueck.sh."
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

# Sperre eines neueren, schon abgelehnten Release behalten (Nachfolger von JETZT, z. B. nach einem automatischen Rückfall):
# sonst spielte der nächste Lauf ihn wieder ein und nähme diesen Rückfall still zurück. Eine Zeile wie bisher (ältere Stände lesen sie so)
git merge-base --is-ancestor "$JETZT" "$(cat .release-abgelehnt 2>/dev/null || true)" 2>/dev/null || echo "$JETZT" > .release-abgelehnt
git reset -q --hard "$VORHER"
# Versionsnummern und Prüfliste aus dem zurückgeholten Commit (dessen eigenes Skript; ältere Stände bringen beides mit)
if [ -f deploy/bereitstellen.py ]; then python3 deploy/bereitstellen.py || echo "Hinweis: Bereitstellung unvollständig – aktualisieren.sh holt sie nach"; fi
# Container-Konfiguration geändert: alle neu erstellen; nur das Image: nur die Anwendungs-Container (Keycloak und seine
# Datenbank laufen weiter); nur die Apache-Konfiguration (einzelne Datei eingebunden): nur der Container der Mitarbeiter-Hosts
mitarbeiter_container() { envwert COMPOSE_FILE | grep -qF "$ANMELDUNG_COMPOSE" && grep -q '^  app-mitarbeiter:' "$ANMELDUNG_COMPOSE" 2>/dev/null; }
if git diff --name-only "$JETZT" "$VORHER" | grep -qE '^(Caddyfile|docker-compose\.yml|deploy/anmeldung/docker-compose\.anmeldung\.yml)$'; then $COMPOSE up -d --force-recreate
elif [ "$BILD" = 1 ]; then
  if mitarbeiter_container; then $COMPOSE up -d --force-recreate app app-mitarbeiter; else $COMPOSE up -d --force-recreate app; fi
elif git diff --name-only "$JETZT" "$VORHER" | grep -qx 'deploy/anmeldung/apache-oidc\.conf'; then
  if mitarbeiter_container; then $COMPOSE up -d --force-recreate app-mitarbeiter; else $COMPOSE up -d --force-recreate app; fi
fi
echo "Zurückgesetzt auf $(git log -1 --format='%h %s')"
