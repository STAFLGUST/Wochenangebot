#!/bin/sh
# Test der Release-Prüfungen (.github/scripts/release-pruefen.sh) mit einem Platzhalter für gh:
# Antworten der GitHub-API liegen als Dateien bereit (bei Folgen: <name>.1, <name>.2, …).
# Prüft: ohne Freigabepflicht kein Release; veraltete Stände werden abgelehnt; CI wird abgewartet;
# fehlgeschlagene CI blockiert; erfolgreicher Lauf zählt nur mit Nachweis-Auftrag (vollständig geprüft oder aus dem
# Pull Request übernommen), nicht wenn alles übersprungen wurde; der Freigebende wird ermittelt.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
S="$REPO/.github/scripts/release-pruefen.sh"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; fi; }

mkdir -p "$T/bin" "$T/api"
cat > "$T/bin/gh" <<'EOF'
#!/bin/sh
[ "$1" = api ] || exit 2
n=$(printf '%s' "$2" | tr -c 'A-Za-z0-9\n' '_')
z="$GH_STUB/.zaehler-$n"; k=$(( $(cat "$z" 2>/dev/null || echo 0) + 1 )); echo "$k" > "$z"
if [ -f "$GH_STUB/$n.$k" ]; then cat "$GH_STUB/$n.$k"; exit 0; fi
i=$k; while [ "$i" -gt 1 ]; do i=$((i - 1)); [ -f "$GH_STUB/$n.$i" ] && { cat "$GH_STUB/$n.$i"; exit 0; }; done
[ -f "$GH_STUB/$n" ] && { cat "$GH_STUB/$n"; exit 0; }
echo '{"message":"Not Found"}'; exit 1
EOF
chmod +x "$T/bin/gh"
export PATH="$T/bin:$PATH" GH_STUB="$T/api" GITHUB_REPOSITORY=o/r TAKT=0
A=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
B=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
datei() { printf '%s' "$1" | tr -c 'A-Za-z0-9\n' '_'; }
setze() { printf '%s' "$2" > "$T/api/$(datei "$1")"; }
leere() { rm -f "$T/api/"* "$T/api/".zaehler-*; }
lauf() { "$@" > "$T/out" 2>&1; }
ENV=repos/o/r/environments/produktion
CI="repos/o/r/actions/workflows/ci.yml/runs?head_sha=$A&branch=main&per_page=20"
lauf_json() { printf '{"workflow_runs":[{"id":41,"head_branch":"main","event":"%s","status":"%s","conclusion":%s}]}' "$1" "$2" "$3"; }
JOBS="repos/o/r/actions/runs/41/jobs?filter=latest&per_page=100"
jobs_json() { printf '{"jobs":[{"name":"Statische Prüfungen","conclusion":"success"},{"name":"%s","conclusion":"%s"}]}' "$1" "$2"; }
VOLL="Vollständig geprüft (Stand $B)"

# --- schutz
ok "schutz: Umgebung fehlt → Abbruch mit Hinweis" "! lauf sh '$S' schutz && grep -q 'Required reviewers' '$T/out'"
setze "$ENV" '{"name":"produktion","protection_rules":[{"type":"branch_policy"}]}'
ok "schutz: ohne Prüfer → Abbruch" "! lauf sh '$S' schutz && grep -q 'verlangt keine Freigabe' '$T/out'"
setze "$ENV" '{"name":"produktion","protection_rules":[{"type":"required_reviewers","reviewers":[]}]}'
ok "schutz: Regel ohne Person → Abbruch" "! lauf sh '$S' schutz"
setze "$ENV" '{"name":"produktion","protection_rules":[{"type":"branch_policy"},{"type":"required_reviewers","reviewers":[{"type":"User","reviewer":{"login":"STAFLGUST"}}]}]}'
ok "schutz: mit Prüfer → ok" "lauf sh '$S' schutz && grep -q 'Freigabepflicht aktiv' '$T/out'"

# --- aktuell
setze repos/o/r/git/ref/heads/main "{\"object\":{\"sha\":\"$A\"}}"
ok "aktuell: Commit ist main → ok" "SHA=$A lauf sh '$S' aktuell"
ok "aktuell: erwarteter Commit stimmt → ok" "SHA=$A ERWARTET=$A lauf sh '$S' aktuell"
ok "aktuell: main inzwischen weiter (erwartet ≠ Lauf) → Abbruch" "! SHA=$A ERWARTET=$B lauf sh '$S' aktuell && grep -q 'inzwischen weiter' '$T/out'"
ok "aktuell: Lauf-Commit nicht mehr neuester → Abbruch" "! SHA=$B lauf sh '$S' aktuell && grep -q 'nicht mehr der neueste' '$T/out'"

# --- ci
leere
setze "$CI" "$(lauf_json push completed '"success"')"
setze "$JOBS" "$(jobs_json "$VOLL" success)"
ok "ci: erfolgreich, vollständig geprüft → ok" "SHA=$A lauf sh '$S' ci"
setze "$JOBS" "$(jobs_json "Prüfung aus Pull Request übernommen" success)"
ok "ci: erfolgreich, Prüfung aus Pull Request übernommen → ok" "SHA=$A lauf sh '$S' ci"
setze "$JOBS" "$(jobs_json "$VOLL" skipped)"
ok "ci: erfolgreich, aber alles übersprungen (kein Nachweis) → Abbruch" "! SHA=$A lauf sh '$S' ci && grep -q 'ohne Nachweis' '$T/out'"
setze "$JOBS" "$(jobs_json "Prüfung aus Pull Request übernommen" skipped)"
ok "ci: Übernahme übersprungen → Abbruch" "! SHA=$A lauf sh '$S' ci"
setze "$JOBS" "$(jobs_json "Vollständig geprüft (alt)" success)"
ok "ci: fremder Auftragsname zählt nicht" "! SHA=$A lauf sh '$S' ci"
rm -f "$T/api/$(datei "$JOBS")"
ok "ci: Aufträge nicht lesbar → Abbruch" "! SHA=$A lauf sh '$S' ci"
leere
setze "$CI" "$(lauf_json push completed '"failure"')"
ok "ci: fehlgeschlagen → Abbruch" "! SHA=$A lauf sh '$S' ci && grep -q 'keinen erfolgreichen CI-Lauf' '$T/out'"
leere
setze "$CI" "$(lauf_json pull_request completed '"success"')"
ok "ci: nur PR-Lauf zählt nicht" "! SHA=$A lauf sh '$S' ci"
leere
folge() { printf '%s' "$3" > "$T/api/$(datei "$1").$2"; }   # Antwort Nr. k
folge "$CI" 1 "$(lauf_json push in_progress null)"
folge "$CI" 2 "$(lauf_json push in_progress null)"
folge "$CI" 3 "$(lauf_json push completed '"success"')"
setze "$JOBS" "$(jobs_json "$VOLL" success)"
ok "ci: läuft noch → wartet, dann ok" "SHA=$A lauf sh '$S' ci && grep -q 'warte' '$T/out' && [ \"\$(cat '$T/api/.zaehler-$(datei "$CI")')\" = 3 ]"
leere
folge "$CI" 1 '{"workflow_runs":[]}'
folge "$CI" 2 "$(lauf_json push completed '"success"')"
setze "$JOBS" "$(jobs_json "$VOLL" success)"
ok "ci: Suche zuerst leer (API), dann gefunden → ok" "SHA=$A lauf sh '$S' ci && grep -q 'frage erneut' '$T/out'"
leere
setze "$CI" '{"workflow_runs":[]}'
ok "ci: dauerhaft kein Lauf → Abbruch nach 3 Abfragen" "! SHA=$A lauf sh '$S' ci && grep -q 'keinen erfolgreichen' '$T/out' && [ \"\$(cat '$T/api/.zaehler-$(datei "$CI")')\" = 3 ]"
leere
setze "$CI" "$(lauf_json push queued null)"
ok "ci: Wartezeit überschritten → Abbruch" "! SHA=$A WARTEN=0 lauf sh '$S' ci && grep -q 'noch nicht fertig' '$T/out'"

# --- freigeber
setze repos/o/r/actions/runs/7/approvals '[{"state":"rejected","user":{"login":"x"}},{"state":"approved","user":{"login":"STAFLGUST"}}]'
ok "freigeber: aus der Freigabe" "[ \"\$(RUN_ID=7 ACTOR=bot sh '$S' freigeber)\" = STAFLGUST ]"
ok "freigeber: API nicht lesbar → Startender" "[ \"\$(RUN_ID=8 ACTOR=bot sh '$S' freigeber)\" = bot ]"
ok "unbekannter Aufruf → Fehler" "! lauf sh '$S' quatsch"

echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" -eq 0 ]
