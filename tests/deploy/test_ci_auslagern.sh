#!/bin/sh
# Test von deploy/ci-kalkulationen-auslagern.php (Kalkulationen des Container-Imports auslagern, GoBD): Export nur für den
# Besitzer lesbar, entfernt werden nur exportierte Einträge; eine seit dem Export gespeicherte Fassung (die Anwendung läuft
# weiter) bricht ohne Änderung ab. Echte Speicherschicht im Wegwerf-Ordner, für den Wettlauf eine Attrappe der Speicherschicht.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
AUS=""; CODE=0
export AUS CODE
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
umask 022
DOK='{"rev":3,"liste":[{"id":"k1","sendung":"s1","fassungen":[{"nr":1,"eingabe":{"positionen":[{"artikel":"A"}]}}]},{"id":"k2","sendung":"s2","fassungen":[{"nr":1,"eingabe":{"positionen":[{"artikel":"B"},{"artikel":"C"}]}}]}]}'
mkdir "$T/daten"; printf '%s\n%s' '<?php http_response_code(404); exit; ?>' "$DOK" > "$T/daten/containerimport-kalkulationen.php"
liste() { python3 -c "import json,sys; t=open(sys.argv[1]).read(); t=t[t.index(chr(10))+1:] if t.startswith('<?php') else t; print(','.join(k['sendung'] for k in json.loads(t)['liste']))" "$1"; }

AUS=$(DATA_DIR="$T/daten" php "$REPO/deploy/ci-kalkulationen-auslagern.php" --export "$T/archiv.json" --entfernen s1 2>&1) && CODE=0 || CODE=$?
ok "Export geprüft, nur der genannte Eintrag entfernt" '[ $CODE = 0 ] && [ "$(liste "$T/daten/containerimport-kalkulationen.php")" = s2 ] && [ "$(liste "$T/archiv.json")" = s1,s2 ] && echo "$AUS" | grep -q "Ausgelagert"'
ok "Exportdatei nur für den Besitzer lesbar (Geschäftsdaten)" '[ "$(stat -c %a "$T/archiv.json")" = 600 ]'

# Wettlauf: zwischen Export und Sperre speichert ein Mitarbeiter eine neue Fassung zu s1 – die Attrappe liefert sie beim zweiten Lesen
mkdir -p "$T/w/deploy" "$T/w/app/api"; cp "$REPO/deploy/ci-kalkulationen-auslagern.php" "$T/w/deploy/"
printf '%s\n' "$DOK" > "$T/w/dok.json"
cat > "$T/w/app/api/storage.php" <<'EOF2'
<?php
function store_read(string $n)
{
    static $mal = 0;
    $d = json_decode((string)file_get_contents(getenv('DOK_DATEI')), true);
    if (++$mal > 1) $d['liste'][0]['fassungen'][] = ['nr' => 2, 'eingabe' => ['positionen' => [['artikel' => 'neu']]]];
    return $d;
}
function with_lock(string $n, callable $f) { return $f(); }
function store_write(string $n, $d) { file_put_contents(getenv('GESCHRIEBEN'), json_encode($d)); }
EOF2
AUS=$(DOK_DATEI="$T/w/dok.json" GESCHRIEBEN="$T/w/geschrieben.json" php "$T/w/deploy/ci-kalkulationen-auslagern.php" --export "$T/w/archiv.json" --entfernen s1 2>&1) && CODE=0 || CODE=$?
ok "neue Fassung seit dem Export: Abbruch, nichts entfernt" '[ $CODE = 1 ] && [ ! -e "$T/w/geschrieben.json" ] && echo "$AUS" | grep -q "seit dem Export geändert"'
AUS=$(DOK_DATEI="$T/w/dok.json" GESCHRIEBEN="$T/w/geschrieben.json" php "$T/w/deploy/ci-kalkulationen-auslagern.php" --export "$T/w/archiv2.json" --entfernen s2 2>&1) && CODE=0 || CODE=$?
ok "… ein unveränderter Eintrag daneben wird weiter entfernt" '[ $CODE = 0 ] && [ "$(liste "$T/w/geschrieben.json")" = s1 ]'
echo "ci-kalkulationen-auslagern.php: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
