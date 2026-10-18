#!/bin/sh
# Test der Datensicherung (deploy/sichern.sh) in einem Wegwerf-Ordner mit Testdaten.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; fi; }
mkdir -p "$T/deploy"; cp "$REPO"/deploy/sichern.sh "$REPO"/deploy/sicherung-pruefen.* "$REPO"/deploy/datenbank.py "$T/deploy/"
cp -r "$REPO/tests/fixtures/data-seed" "$T/daten"
printf '%s\n{"key":"dGVzdA=="}' '<?php http_response_code(404); exit; ?>' > "$T/daten/mail-schluessel.php"
st() { python3 -c "import json; t=open('$T/daten/sicherung.php').read(); print(json.loads(t[t.index(chr(10))+1:]).get('$1'))"; }

sh "$T/deploy/sichern.sh" >/dev/null
ok "Sicherung erstellt und geprüft" '[ "$(st ok)" = True ] && [ "$(st inhalt)" = True ] && [ "$(ls "$T"/sicherungen/daten-*.tar.gz | wc -l)" -eq 1 ]'
ok "Archiv nur für root lesbar" '[ "$(stat -c %a "$T/sicherungen")" = 700 ] && [ "$(stat -c %a "$T"/sicherungen/daten-*.tar.gz)" = 600 ]'
ok "Archiv enthält die Daten" 'tar tzf "$T"/sicherungen/daten-*.tar.gz | grep -q angebot.php'
ok "Schlüssel für das Postfach-Passwort wird nicht gesichert" '! tar tzf "$T"/sicherungen/daten-*.tar.gz | grep -q mail-schluessel'
sh "$T/deploy/sichern.sh" >/dev/null
ok "innerhalb von 23 Stunden keine zweite Sicherung" '[ "$(ls "$T"/sicherungen/daten-*.tar.gz | wc -l)" -eq 1 ]'
echo '{kaputt' > "$T/daten/defekt.php"; sleep 1
sh "$T/deploy/sichern.sh" --jetzt >/dev/null || true
ok "defekte Datei wird erkannt" '[ "$(st ok)" = False ] && [ "$(st fehler)" = 1 ]'
rm "$T/daten/defekt.php"
mv "$T/sicherungen" "$T/s2"; touch "$T/sicherungen"   # Ablage nicht anlegbar → unerwarteter Abbruch
sh "$T/deploy/sichern.sh" --jetzt >/dev/null 2>&1 || true
ok "unerwarteter Abbruch hinterlässt Fehlerstatus" '[ "$(st ok)" = False ] && grep -q "Abbruch" "$T/daten/sicherung.php"'
rm "$T/sicherungen"; mv "$T/s2" "$T/sicherungen"
# Database backup must use a snapshot and verify its actual contents.
python3 "$T/deploy/datenbank.py" migrate "$T/daten" --offline >/dev/null
sleep 1
sh "$T/deploy/sichern.sh" --jetzt >/dev/null
ok "SQLite-Sicherung erstellt und geprüft" '[ "$(st ok)" = True ] && [ "$(st inhalt)" = True ]'
LATEST=$(ls -1t "$T"/sicherungen/daten-*.tar.gz | head -1)
mkdir "$T/restore"
tar xzf "$LATEST" -C "$T/restore"
ok "SQLite-Archiv enthält geprüfte Datenbank" 'python3 "$T/deploy/datenbank.py" check "$T/restore" >/dev/null'
ok "SQLite-Archiv enthält keinen Postfachschlüssel" '[ ! -f "$T/restore/mail-schluessel.php" ]'
printf 'broken' > "$T/restore/.sqlite/store.sqlite"
ok "Beschädigte Datenbank im Archiv erkannt" '[ "$(python3 "$T/deploy/sicherung-pruefen.py" "$T/restore")" -gt 0 ]'
echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" -eq 0 ]
