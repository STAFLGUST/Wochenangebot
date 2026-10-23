#!/bin/sh
# Release-Modus: spielt nur einen von Hand freigegebenen Commit ein (GitHub-Workflow „Release“),
# prüft danach die Erreichbarkeit wie ein Besucher und kehrt bei Fehlern automatisch zur Vorversion zurück.
# Wird von aktualisieren.sh aufgerufen, sobald der Release-Modus eingerichtet ist
# (deploy/release-modus-einrichten.sh). Ohne diese Einrichtung ändert sich nichts.
#
# Benötigt in .env (nur für root lesbar):
#   GITHUB_REPO=STAFLGUST/Wochenangebot
#   GITHUB_TOKEN_LESEN=…   fein granularer Token: nur dieses Repository, nur Lesen (Contents, Actions, Metadata)
# Optional:
#   HC_DEPLOY_URL=https://…  Totmannschalter/Benachrichtigung (bei Fehler wird „/fail“ angehängt)
#
# Sicherung vor dem Einspielen mit dem Sicherungsskript des NEUEN Commits (ein Fehler im alten Skript blockiert sonst
# auch das Release mit der Korrektur). Es läuft als deploy/.sichern-release.sh und nutzt die übrigen Dateien in deploy/
# (datenbank.py, sicherung-pruefen.*) noch im alten Stand.
# Anwendungs-Image (deploy/image): Ist die Ergänzungsdatei der Anmeldung über COMPOSE_FILE in .env aktiv und ändert das
# Release deploy/image/, wird das Image vorab als stafl-app:release-neu gebaut (Code bleibt bis dahin unverändert), erst
# beim Einspielen auf den aktiven Namen umgetaggt; das bisherige Image bleibt als stafl-app:release-vorher für den Rückfall
# (auch für den manuellen Notfall-Rückfall deploy/release-zurueck.sh). Nach erfolgreichem Healthcheck werden hängende
# Images ohne Namen entfernt (docker image prune -f).
# Bereitstellung (deploy/bereitstellen.py des eingespielten Stands): nach jedem Codewechsel setzt sie die Versionsnummern
# der Skripte/Stylesheets und erzeugt die Prüfliste der Dateiprüfung aus genau diesem Commit. Fehlt sie oder schlägt sie
# fehl, bleibt die Seite korrekt (Dateien ohne Nummer werden mit Rückfrage geladen); aktualisieren.sh holt sie nach.
#
# Für Tests überschreibbar: WA_BASIS, WA_API (GitHub-API), WA_HEALTH_URL, WA_HEALTH_HOST, WA_COMPOSE, WA_DOCKER, WA_SICHERN
set -eu
BASIS=${WA_BASIS:-/opt/wochenangebot}
cd "$BASIS"
envwert() { sed -n "s/^$1=//p" "$BASIS/.env" 2>/dev/null | head -1 | tr -d '"'"'"' '; }
REPO=${WA_REPO:-$(envwert GITHUB_REPO)}
TOKEN=$(envwert GITHUB_TOKEN_LESEN)
API=${WA_API:-https://api.github.com}
DOMAIN=$(envwert DOMAIN)
HEALTH_URL=${WA_HEALTH_URL:-https://$DOMAIN}
HEALTH_HOST=${WA_HEALTH_HOST:-$DOMAIN:443:127.0.0.1}
COMPOSE=${WA_COMPOSE:-docker compose}
DOCKER=${WA_DOCKER:-docker}
ANMELDUNG_COMPOSE=deploy/anmeldung/docker-compose.anmeldung.yml
APP_VERSION=$(envwert STAFL_APP_VERSION)
APP_BILD="stafl-app:${APP_VERSION:-lokal}"   # Name wie in der Ergänzungsdatei: stafl-app:${STAFL_APP_VERSION:-lokal}
BILD_NEU=stafl-app:release-neu
BILD_VORHER=stafl-app:release-vorher
SICHERN_NEU="$BASIS/deploy/.sichern-release.sh"
trap 'rm -f "$SICHERN_NEU"' EXIT
trap 'exit 1' HUP INT TERM
BAUEN=0
HC_URL=$(envwert HC_DEPLOY_URL)
STATUS="$BASIS/daten/deployment.php"
GUARD='<?php http_response_code(404); exit; ?>'

[ -n "$REPO" ] && [ -n "$TOKEN" ] || { echo "Release-Modus: GITHUB_REPO oder GITHUB_TOKEN_LESEN fehlt in .env"; exit 1; }

api() { curl -fsS -m 20 -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" "$API/repos/$REPO/$1"; }
melden() { [ -n "$HC_URL" ] || return 0; if [ "$1" = ok ]; then curl -fsS -m 10 --retry 3 "$HC_URL" >/dev/null 2>&1 || true; else curl -fsS -m 10 --retry 3 "$HC_URL/fail" >/dev/null 2>&1 || true; fi; }
status() { # ok sha vorher lauf meldung
  printf '%s\n{"t":"%s","ok":%s,"sha":"%s","vorher":"%s","lauf":"%s","meldung":"%s"}' "$GUARD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" "$5" > "$STATUS.tmp"
  chown 33:33 "$STATUS.tmp" 2>/dev/null || true; chmod 644 "$STATUS.tmp"; mv "$STATUS.tmp" "$STATUS"
}
angebot_ok() { # Angebots-API antwortet: öffentlich (200, ok:true), mit der Aufforderung zur Anmeldung, wenn das
  # Wochenangebot nur für Kunden sichtbar ist (401), oder mit dem Hinweis auf den Wartungsmodus (503, wartung:true)
  ANT=$(curl -sS -m 5 --resolve "$HEALTH_HOST" -w '\n%{http_code}' "$HEALTH_URL/api/?action=offer" 2>/dev/null) || return 1
  CODE=$(printf '%s' "$ANT" | tail -n 1)
  { [ "$CODE" = 200 ] && printf '%s' "$ANT" | grep -q '"ok":true'; } || { [ "$CODE" = 401 ] && printf '%s' "$ANT" | grep -q '"ok":false'; } \
    || { [ "$CODE" = 503 ] && printf '%s' "$ANT" | grep -q '"wartung":true'; }   # Wartungsmodus eingeschaltet
}
gesund() { # Status-API, Angebot, Startseite und Eingabebereich wie ein Besucher über Caddy;
  # erst nach 3 s (Caches von PHP/Webserver), dann zwei erfolgreiche Prüfungen hintereinander, insgesamt bis zu 40 s
  sleep 3
  i=0; gut=0
  while [ $i -lt 20 ]; do
    if curl -fsS -m 5 --resolve "$HEALTH_HOST" "$HEALTH_URL/api/?action=status" 2>/dev/null | grep -q '"ok":true' \
      && angebot_ok \
      && curl -fsS -m 5 --resolve "$HEALTH_HOST" "$HEALTH_URL/" 2>/dev/null | grep -q 'assets/frontend.js' \
      && curl -fsS -m 5 --resolve "$HEALTH_HOST" "$HEALTH_URL/admin/" 2>/dev/null | grep -q 'assets/admin.js'; then
      gut=$((gut + 1)); [ $gut -ge 2 ] && return 0
    else
      gut=0
    fi
    i=$((i + 1)); sleep 2
  done
  return 1
}
bereitstellen() { # Versionsnummern und Prüfliste aus dem aktiven Commit (Skript des aktiven Stands; ältere Stände bringen beides mit)
  [ -f deploy/bereitstellen.py ] || return 0
  python3 deploy/bereitstellen.py || echo "Hinweis: Bereitstellung (Versionsnummern/Prüfliste) unvollständig – nächster Versuch beim nächsten Lauf"
}
einspielen() { # sha vorher [zurueck]: Code wechseln; Container nur neu erstellen, wenn sich Konfiguration oder Image ändern
  if [ -f daten/.sqlite-active ] && ! git cat-file -e "$1:app/api/storage.php" 2>/dev/null; then
    echo "SQLite aktiv: Vor einem Rückfall auf Dateispeicherung erst deploy/datenbank-umschalten.sh rollback ausführen."
    return 1
  fi
  if [ "$BAUEN" = 1 ] && [ "${3:-}" = zurueck ]; then
    $DOCKER tag "$BILD_VORHER" "$APP_BILD" || echo "Altes Image $BILD_VORHER nicht gefunden – App läuft mit dem neuen Image"
  elif [ "$BAUEN" = 1 ]; then
    $DOCKER tag "$APP_BILD" "$BILD_VORHER" || true   # für den Rückfall merken
    $DOCKER tag "$BILD_NEU" "$APP_BILD"
  fi
  git reset -q --hard "$1"
  bereitstellen
  # Container-Konfiguration: Caddyfile, docker-compose.yml und die Ergänzungsdatei der Anmeldung (COMPOSE_FILE in .env);
  # nur das Image geändert: nur die App neu erstellen (Keycloak und seine Datenbank laufen weiter)
  # Apache-Konfiguration der Anmeldung (als einzelne Datei eingebunden: nach dem Codewechsel sähe der Container sonst
  # weiter die alte Fassung) → nur die App neu erstellen
  if git diff --name-only "$2" "$1" | grep -qE '^(Caddyfile|docker-compose\.yml|deploy/anmeldung/docker-compose\.anmeldung\.yml)$'; then $COMPOSE up -d --force-recreate
  elif [ "$BAUEN" = 1 ] || git diff --name-only "$2" "$1" | grep -qx 'deploy/anmeldung/apache-oidc\.conf'; then $COMPOSE up -d --force-recreate app; fi
}

# 1. Neuester erfolgreicher, von Hand gestarteter Release-Lauf auf main
LAUF=$(api "actions/workflows/release.yml/runs?branch=main&event=workflow_dispatch&status=success&per_page=1") || { echo "GitHub-API nicht erreichbar"; exit 1; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); $1" ; }
SHA=$(printf '%s' "$LAUF" | json "r=(d.get('workflow_runs') or [{}])[0]; print(r.get('head_sha','') if r.get('path')=='.github/workflows/release.yml' and r.get('head_branch')=='main' and r.get('conclusion')=='success' else '')")
LAUF_ID=$(printf '%s' "$LAUF" | json "print((d.get('workflow_runs') or [{}])[0].get('id',''))")
[ -n "$SHA" ] || exit 0                       # noch kein Release
AKTUELL=$(git rev-parse HEAD)
[ "$SHA" = "$AKTUELL" ] && exit 0             # schon live
ABGELEHNT="$BASIS/.release-abgelehnt"
[ "$SHA" = "$(cat "$ABGELEHNT" 2>/dev/null)" ] && exit 0   # schon einmal abgelehnt/zurückgesetzt → nicht erneut versuchen
ablehnen() { echo "$SHA" > "$ABGELEHNT"; status false "$AKTUELL" "$AKTUELL" "$LAUF_ID" "$1"; melden fail; echo "$1"; exit 1; }
printf '%s' "$SHA" | grep -qE '^[0-9a-f]{40}$' || { echo "Ungültige Commit-Kennung"; exit 1; }

# 2. CI für genau diesen Commit erfolgreich?
CI=$(api "actions/workflows/ci.yml/runs?head_sha=$SHA&status=success&per_page=20") || { echo "GitHub-API nicht erreichbar"; exit 1; }
N=$(printf '%s' "$CI" | json "print(sum(1 for r in d.get('workflow_runs', []) if r.get('head_branch')=='main' and r.get('conclusion')=='success'))")
[ "$N" -ge 1 ] || ablehnen "Release $SHA ohne erfolgreiche CI – nicht eingespielt"

# 3. Commit holen und prüfen, dass er auf main liegt
git fetch -q origin main
git cat-file -e "$SHA^{commit}" 2>/dev/null || ablehnen "Commit $SHA liegt nicht auf main – nicht eingespielt"
git merge-base --is-ancestor "$SHA" origin/main || ablehnen "Commit $SHA liegt nicht auf main – nicht eingespielt"

# 4. Anwendungs-Image vorab bauen, wenn das Release deploy/image/ ändert und die App dieses Image nutzt (COMPOSE_FILE).
#    Nur Bauplan und Compose-Dateien des neuen Stands auschecken, bauen, sofort zurück: App-Code und laufende Container
#    bleiben unverändert. Fehlschlag → nicht eingespielt, nächster Versuch beim nächsten Lauf (noch keine Sicherung erstellt).
if git diff --name-only "$AKTUELL" "$SHA" | grep -q '^deploy/image/' && envwert COMPOSE_FILE | grep -qF "$ANMELDUNG_COMPOSE"; then
  BAUEN=1
  if rm -rf deploy/image && git checkout -q "$SHA" -- deploy/image docker-compose.yml "$ANMELDUNG_COMPOSE" && STAFL_APP_VERSION=release-neu $COMPOSE build --pull app; then
    git reset -q --hard "$AKTUELL"
  else
    git reset -q --hard "$AKTUELL"
    status false "$AKTUELL" "$AKTUELL" "$LAUF_ID" "Anwendungs-Image des Release konnte nicht gebaut werden – nicht eingespielt, bisheriger Stand bleibt aktiv (nächster Versuch beim nächsten Lauf)"
    melden fail; echo "Image-Bau fehlgeschlagen – Release nicht eingespielt"; exit 1
  fi
fi

# 5. Sicherung vor dem Einspielen mit dem Sicherungsskript des neuen Commits (fehlt es dort: vorhandenes Skript);
#    ohne Sicherung kein Release
if [ -n "${WA_SICHERN:-}" ]; then
  SICHERN=$WA_SICHERN
elif git show "$SHA:deploy/sichern.sh" > "$SICHERN_NEU" 2>/dev/null; then
  SICHERN="sh $SICHERN_NEU --jetzt"
else
  rm -f "$SICHERN_NEU"; SICHERN="sh deploy/sichern.sh --jetzt"
fi
$SICHERN >/dev/null || { status false "$AKTUELL" "$AKTUELL" "$LAUF_ID" "Sicherung vor dem Release fehlgeschlagen – nicht eingespielt (nächster Versuch beim nächsten Lauf)"; melden fail; echo "Sicherung fehlgeschlagen – Release nicht eingespielt"; exit 1; }

rm -f "$SICHERN_NEU"

# 6. Einspielen, prüfen, bei Fehler zurück
einspielen "$SHA" "$AKTUELL"
if gesund; then
  status true "$SHA" "$AKTUELL" "$LAUF_ID" ""
  melden ok
  echo "Release eingespielt: $(git log -1 --format='%h %s')"
  # Aufräumen: nur hängende Images ohne Namen (z. B. das von release-vorher verdrängte); getaggte und laufende Images
  # sowie Volumes bleiben. Ein Fehler hier ändert nichts am erfolgreichen Release.
  $DOCKER image prune -f || echo "Hinweis: Aufräumen alter Images fehlgeschlagen – Release ist trotzdem eingespielt."
  exit 0
fi
echo "Healthcheck fehlgeschlagen – zurück auf $AKTUELL"
echo "$SHA" > "$ABGELEHNT"
einspielen "$AKTUELL" "$SHA" zurueck
if gesund; then
  status false "$AKTUELL" "$SHA" "$LAUF_ID" "Release $SHA fehlerhaft – automatisch auf Vorversion zurückgesetzt"
else
  status false "$AKTUELL" "$SHA" "$LAUF_ID" "Release $SHA fehlerhaft – Rückfall durchgeführt, Seite antwortet aber nicht. Sofort prüfen!"
fi
melden fail
exit 1
