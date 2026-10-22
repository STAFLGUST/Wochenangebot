#!/bin/sh
# Prüfungen des Release-Laufs (.github/workflows/release.yml). Läuft auf dem GitHub-Runner, nachdem die
# Freigabe in der Umgebung „produktion“ erteilt wurde. Jede Prüfung bricht mit einer verständlichen
# Meldung ab – dann wird nichts markiert und der Server spielt nichts ein.
#
#   schutz     Umgebung „produktion“ verlangt eine Freigabe durch mindestens eine Person
#   aktuell    der Commit ist noch der neueste Stand von main (und der erwartete Commit, falls angegeben)
#   ci         CI für genau diesen Commit auf main erfolgreich (wartet, solange sie noch läuft) – mit Nachweis-Auftrag
#              „Vollständig geprüft (Stand …)“ oder „Prüfung aus Pull Request übernommen“ (ci.yml)
#   freigeber  gibt aus, wer die Freigabe erteilt hat (sonst den Startenden)
#
# Umgebung: GITHUB_REPOSITORY, SHA, optional ERWARTET, UMGEBUNG (produktion), RUN_ID, ACTOR,
#           WARTEN (Sekunden, 600), TAKT (Sekunden, 10). Benötigt gh (mit GH_TOKEN) und jq.
set -eu
REPO=${GITHUB_REPOSITORY:?}
UMGEBUNG=${UMGEBUNG:-produktion}
kurz() { printf "%.7s" "$1"; }
fehler() { echo "::error::$1"; exit 1; }

case "${1:-}" in
schutz)
  env_json=$(gh api "repos/${REPO}/environments/${UMGEBUNG}" 2>/dev/null) \
    || fehler "Umgebung '${UMGEBUNG}' nicht lesbar. Einrichten: Settings → Environments → ${UMGEBUNG} → Required reviewers."
  n=$(printf '%s' "$env_json" | jq '[.protection_rules[]? | select(.type == "required_reviewers") | .reviewers[]?] | length')
  [ "$n" -ge 1 ] \
    || fehler "Umgebung '${UMGEBUNG}' verlangt keine Freigabe. Ohne Freigabe wird nichts veröffentlicht. Einrichten: Settings → Environments → ${UMGEBUNG} → Required reviewers."
  echo "Freigabepflicht aktiv (${n} berechtigte Person/Team)."
  ;;
aktuell)
  SHA=${SHA:?}
  if [ -n "${ERWARTET:-}" ] && [ "$ERWARTET" != "$SHA" ]; then
    fehler "main ist inzwischen weiter ($(kurz "$SHA") statt $(kurz "$ERWARTET")). Für den neueren Stand wartet ein eigener Release-Lauf."
  fi
  kopf=$(gh api "repos/${REPO}/git/ref/heads/main" | jq -r '.object.sha')
  [ "$kopf" = "$SHA" ] \
    || fehler "Commit $(kurz "$SHA") ist nicht mehr der neueste Stand von main ($(kurz "$kopf")). Bitte den neueren Release-Lauf freigeben."
  echo "Commit $(kurz "$SHA") ist der aktuelle Stand von main."
  ;;
ci)
  SHA=${SHA:?}
  bis=$(( $(date +%s) + ${WARTEN:-600} ))
  leer=0
  while :; do
    laeufe=$(gh api "repos/${REPO}/actions/workflows/ci.yml/runs?head_sha=${SHA}&branch=main&per_page=20" \
      | jq '[.workflow_runs[] | select(.head_branch == "main" and (.event == "push" or .event == "workflow_dispatch"))]')
    ok=$(printf '%s' "$laeufe" | jq '[.[] | select(.conclusion == "success")] | length')
    offen=$(printf '%s' "$laeufe" | jq '[.[] | select(.status != "completed")] | length')
    # Ein erfolgreicher Lauf zählt nur mit Nachweis: „Vollständig geprüft (Stand …)“ (alle Aufträge grün) oder
    # „Prüfung aus Pull Request übernommen“. Schutz gegen Läufe, in denen alles übersprungen wurde (auch das ist „success“).
    for id in $(printf '%s' "$laeufe" | jq -r '.[] | select(.conclusion == "success") | .id'); do
      n=$(gh api "repos/${REPO}/actions/runs/${id}/jobs?filter=latest&per_page=100" | jq '[.jobs[] | select(.conclusion == "success"
        and ((.name | startswith("Vollständig geprüft (Stand ")) or .name == "Prüfung aus Pull Request übernommen"))] | length') || n=0
      if [ "${n:-0}" -ge 1 ]; then echo "CI für ${SHA} erfolgreich (Lauf ${id})."; exit 0; fi
      echo "CI-Lauf ${id} ist erfolgreich, enthält aber keinen Nachweis (Vollständig geprüft / Prüfung übernommen)."
    done
    if [ "$ok" -ge 1 ] && [ "$offen" -eq 0 ]; then
      fehler "CI für ${SHA} war erfolgreich, aber ohne Nachweis einer vollständigen Prüfung. CI auf main neu starten."
    fi
    # Die gefilterte Läufe-Suche der API liefert gelegentlich kurz eine leere Liste – dann bis zu zweimal nachfragen.
    if [ "$(printf '%s' "$laeufe" | jq 'length')" -eq 0 ] && [ "$leer" -lt 2 ]; then
      leer=$((leer + 1)); echo "Kein CI-Lauf gefunden – frage erneut nach …"; sleep "${TAKT:-10}"; continue
    fi
    [ "$offen" -ge 1 ] || fehler "Für Commit ${SHA} gibt es keinen erfolgreichen CI-Lauf auf main. Erst CI abwarten bzw. reparieren."
    [ "$(date +%s)" -lt "$bis" ] || fehler "CI für ${SHA} ist nach ${WARTEN:-600} s noch nicht fertig. Release später erneut starten."
    echo "CI läuft noch – warte …"
    sleep "${TAKT:-10}"
  done
  ;;
freigeber)
  wer=""
  if [ -n "${RUN_ID:-}" ]; then
    wer=$(gh api "repos/${REPO}/actions/runs/${RUN_ID}/approvals" 2>/dev/null \
      | jq -r '[.[] | select(.state == "approved") | .user.login] | last // empty' 2>/dev/null) || wer=""
  fi
  echo "${wer:-${ACTOR:-unbekannt}}"
  ;;
*)
  echo "Aufruf: $0 schutz|aktuell|ci|freigeber" >&2; exit 2
  ;;
esac
