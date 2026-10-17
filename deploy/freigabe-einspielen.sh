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
# Für Tests überschreibbar: WA_BASIS, WA_API (GitHub-API), WA_HEALTH_URL, WA_HEALTH_HOST, WA_COMPOSE, WA_SICHERN
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
SICHERN=${WA_SICHERN:-sh deploy/sichern.sh --jetzt}
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
angebot_ok() { # Angebots-API antwortet: öffentlich (200, ok:true) oder – wenn das Wochenangebot nur für
  # angemeldete Kunden sichtbar ist – mit der Aufforderung zur Anmeldung (401, gültige JSON-Antwort der API)
  ANT=$(curl -sS -m 5 --resolve "$HEALTH_HOST" -w '\n%{http_code}' "$HEALTH_URL/api/?action=offer" 2>/dev/null) || return 1
  CODE=$(printf '%s' "$ANT" | tail -n 1)
  { [ "$CODE" = 200 ] && printf '%s' "$ANT" | grep -q '"ok":true'; } || { [ "$CODE" = 401 ] && printf '%s' "$ANT" | grep -q '"ok":false'; }
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
einspielen() { # sha vorher: Code wechseln; Container nur neu erstellen, wenn sich ihre Konfiguration ändert
  git reset -q --hard "$1"
  if git diff --name-only "$2" "$1" | grep -qE '^(Caddyfile|docker-compose\.yml)$'; then $COMPOSE up -d --force-recreate; fi
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

# 4. Sicherung vor dem Einspielen; ohne Sicherung kein Release
$SICHERN >/dev/null || { status false "$AKTUELL" "$AKTUELL" "$LAUF_ID" "Sicherung vor dem Release fehlgeschlagen – nicht eingespielt (nächster Versuch beim nächsten Lauf)"; melden fail; echo "Sicherung fehlgeschlagen – Release nicht eingespielt"; exit 1; }

# 5. Einspielen, prüfen, bei Fehler zurück
einspielen "$SHA" "$AKTUELL"
if gesund; then
  status true "$SHA" "$AKTUELL" "$LAUF_ID" ""
  melden ok
  echo "Release eingespielt: $(git log -1 --format='%h %s')"
  exit 0
fi
echo "Healthcheck fehlgeschlagen – zurück auf $AKTUELL"
echo "$SHA" > "$ABGELEHNT"
einspielen "$AKTUELL" "$SHA"
if gesund; then
  status false "$AKTUELL" "$SHA" "$LAUF_ID" "Release $SHA fehlerhaft – automatisch auf Vorversion zurückgesetzt"
else
  status false "$AKTUELL" "$SHA" "$LAUF_ID" "Release $SHA fehlerhaft – Rückfall durchgeführt, Seite antwortet aber nicht. Sofort prüfen!"
fi
melden fail
exit 1
