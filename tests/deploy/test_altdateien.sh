#!/bin/sh
# Test von deploy/altdateien.sh (Altdateien nach der Umschaltung auf SQLite) – echtes deploy/datenbank.py in einem
# Wegwerf-Ordner mit synthetischen Datensätzen, Platzhalter nur für die Sicherung (keine echten Daten, kein Container).
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
export AUS CODE VORHER
G='<?php http_response_code(404); exit; ?>'
neu() {   # Installation mit Datenordner im Dateibetrieb
  rm -rf "$T/i"; mkdir -p "$T/i/deploy" "$T/i/daten/kunden" "$T/i/daten/protokoll" "$T/i/daten/geo"; : > "$T/aufrufe"
  cp "$REPO/deploy/altdateien.sh" "$REPO/deploy/datenbank.py" "$T/i/deploy/"
  printf '#!/bin/sh\necho "sichern $*" >> "%s/aufrufe"\n' "$T" > "$T/i/deploy/sichern.sh"
  cd "$T/i/daten"
  printf '%s\n{"rev":3,"titel":"Testangebot"}' "$G" > angebot.php
  printf '%s\n{"name":"Muster GmbH"}' "$G" > kunden/k1.php
  printf '%s\n[{"t":"2026-10-01","was":"Test"}]' "$G" > protokoll/2026-10.php
  printf '%s\n{"schluessel":"nur-ein-test"}' "$G" > mail-schluessel.php
  printf '%s\n{"ok":true}' "$G" > sicherung.php
  printf '%s\n{"commit":"abc"}' "$G" > deployment.php
  printf '%s\n' "$G" > index.php
  printf 'geo-test' > geo/laender.dat.php
  : > .storage.lock; : > .hr-abwesenheiten.lock
  cd "$T/i"
}
lauf() { AUS=$(cd "$T/i" && sh deploy/altdateien.sh "$@" 2>&1) && CODE=0 || CODE=$?; }
stand() { (cd "$T/i/daten" && find . -type f -exec sha256sum {} + | sort); }

neu
VORHER=$(stand)
lauf zeigen
ok "Dateibetrieb: Abbruch, nichts geändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht aktiv" && [ "$(stand)" = "$VORHER" ] && [ ! -s "$T/aufrufe" ]'
lauf archivieren
ok "Dateibetrieb: archivieren ebenso abgelehnt" '[ $CODE = 1 ] && [ "$(stand)" = "$VORHER" ] && [ ! -d sicherungen ]'

python3 deploy/datenbank.py migrate daten --offline >/dev/null
VORHER=$(stand)
lauf zeigen
ok "zeigen: genau die drei Datensätze, keine Sidecars, geo, index.php" '[ $CODE = 0 ] && echo "$AUS" | grep -q "3 old data files" && echo "$AUS" | grep -q "kunden/k1.php" && ! echo "$AUS" | grep -q "mail-schluessel\|sicherung.php\|deployment\|index.php\|geo/"'
ok "zeigen: ändert nichts" '[ "$(stand)" = "$VORHER" ] && [ ! -s "$T/aufrufe" ] && [ ! -d sicherungen ]'

lauf archivieren
A=$(ls sicherungen/altdateien-*.tar.gz 2>/dev/null | head -1)
ok "archivieren: erst Sicherung, dann Archiv mit Rechten 600" '[ $CODE = 0 ] && grep -qx "sichern --jetzt" "$T/aufrufe" && [ -n "$A" ] && [ "$(stat -c %a "$A")" = 600 ] && [ "$(stat -c %a sicherungen)" = 700 ]'
ok "Archiv enthält genau die Altdateien" '[ "$(tar -tzf "$A" | sort | tr "\n" " ")" = "angebot.php kunden/k1.php protokoll/2026-10.php " ]'
ok "Altdateien entfernt, leere Unterordner auch" '[ ! -e daten/angebot.php ] && [ ! -e daten/kunden ] && [ ! -e daten/protokoll ]'
ok "bleiben: Datenbank, Schalter, Schlüssel, Statusdateien, index.php, geo, Sperren" '[ -f daten/.sqlite/store.sqlite ] && [ -f daten/.sqlite-active ] && [ -f daten/mail-schluessel.php ] && [ -f daten/sicherung.php ] && [ -f daten/deployment.php ] && [ -f daten/index.php ] && [ -f daten/geo/laender.dat.php ] && [ -f daten/.storage.lock ] && [ -f daten/.hr-abwesenheiten.lock ]'
ok "Datenbank danach fehlerfrei" 'python3 deploy/datenbank.py check daten | grep -q "3 documents verified"'
mkdir "$T/ansehen" && tar -xzf "$A" -C "$T/ansehen"
ok "Archiv entpackt: Inhalt unverändert" 'grep -q "Muster GmbH" "$T/ansehen/kunden/k1.php"'

: > "$T/aufrufe"
lauf archivieren
ok "zweiter Lauf: nichts mehr zu archivieren, kein neues Archiv" '[ $CODE = 0 ] && echo "$AUS" | grep -q "nothing archived" && [ "$(ls sicherungen/altdateien-*.tar.gz | wc -l)" = 1 ]'

python3 deploy/datenbank.py rollback daten --offline >/dev/null
ok "Rückweg auf Dateien funktioniert danach (alles aus der Datenbank)" '[ ! -f daten/.sqlite-active ] && grep -q "Muster GmbH" daten/kunden/k1.php && grep -q "Testangebot" daten/angebot.php && [ -f daten/protokoll/2026-10.php ]'

# Beschädigte Datenbank: Abbruch vor jeder Änderung
neu; python3 deploy/datenbank.py migrate daten --offline >/dev/null
printf 'kaputt' > daten/.sqlite/store.sqlite
VORHER=$(stand)
lauf archivieren
ok "beschädigte Datenbank: Abbruch, keine Sicherung, nichts entfernt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Datenbankprüfung" && [ ! -s "$T/aufrufe" ] && [ "$(stand)" = "$VORHER" ]'

# Unerwarteter Eintrag (symbolische Verknüpfung): Abbruch, bevor etwas entfernt wird
neu; python3 deploy/datenbank.py migrate daten --offline >/dev/null
ln -s ../angebot.php daten/kunden/verweis.php
lauf archivieren
ok "Verknüpfung im Datenordner: Abbruch, Altdateien bleiben, kein Archiv" '[ $CODE = 1 ] && [ -f daten/angebot.php ] && [ -f daten/kunden/k1.php ] && [ -z "$(ls sicherungen/altdateien-* 2>/dev/null)" ]'

lauf unsinn
ok "unbekannte Aktion abgelehnt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Aufruf:"'

echo "$PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
