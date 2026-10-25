#!/bin/sh
# Test von deploy/datenbank-umschalten.sh – Vorprüfung vor Sicherung und Stopp, mit Platzhaltern für docker,
# sichern.sh und datenbank.py in einem Wegwerf-Ordner (keine echten Daten, kein Container).
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
cat > "$T/docker" <<STUB
#!/bin/sh
echo "docker \$*" >> "$T/aufrufe"
STUB
chmod +x "$T/docker"
export DOCKER="$T/docker" AUS CODE
neu() {   # frische Installation: Skript, Platzhalter für Sicherung und Datenbankwerkzeug
  rm -rf "$T/i"; mkdir -p "$T/i/deploy" "$T/i/daten"; : > "$T/aufrufe"
  cp "$REPO/deploy/datenbank-umschalten.sh" "$T/i/deploy/"
  printf '#!/bin/sh\necho "sichern $*" >> "%s/aufrufe"\n' "$T" > "$T/i/deploy/sichern.sh"
  cat > "$T/i/deploy/datenbank.py" <<PY
import pathlib, sys
open('$T/aufrufe', 'a').write('datenbank ' + ' '.join(sys.argv[1:]) + '\n')
if pathlib.Path('$T/fehler').exists(): sys.exit(1)
d = pathlib.Path(sys.argv[2])
if sys.argv[1] == 'migrate':
    (d / '.sqlite').mkdir(); (d / '.sqlite' / 'store.sqlite').write_text(''); (d / '.sqlite-active').write_text('1\n')
else:
    (d / '.sqlite-active').unlink()
PY
  touch "$T/i/daten/.storage.lock"
}
lauf() { AUS=$(cd "$T/i" && sh deploy/datenbank-umschalten.sh "$@" 2>&1) && CODE=0 || CODE=$?; }
# chown auf 33:33 braucht root – im Test als normaler Nutzer: chown durch Platzhalter ersetzen
mkdir "$T/bin"; printf '#!/bin/sh\nexit 0\n' > "$T/bin/chown"; chmod +x "$T/bin/chown"; export PATH="$T/bin:$PATH"

neu; touch "$T/i/daten/.sqlite-active"; mkdir "$T/i/daten/.sqlite"
lauf migrate
ok "bereits aktiv: Erfolg mit Hinweis" '[ $CODE = 0 ] && echo "$AUS" | grep -q "bereits aktiv"'
ok "bereits aktiv: keine Sicherung, kein Stopp, kein Datenbankaufruf" '[ ! -s "$T/aufrufe" ]'

neu; mkdir "$T/i/daten/.sqlite"
lauf migrate
ok "alte Datenbank ohne Marker: Abbruch vor dem Stoppen" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nichts geändert" && [ ! -s "$T/aufrufe" ]'

neu
lauf rollback
ok "Rückfall ohne aktives SQLite: nichts zu tun, kein Stopp" '[ $CODE = 0 ] && echo "$AUS" | grep -q "nicht aktiv" && [ ! -s "$T/aufrufe" ]'

neu
lauf migrate
ok "Umschalten: Sicherung, Prüfung im Container, Stopp, Übernahme, Start in dieser Reihenfolge" '[ $CODE = 0 ] && [ "$(cut -d" " -f1-3 "$T/aufrufe" | tr "\n" "|")" = "sichern --jetzt|docker compose exec|docker compose stop|datenbank migrate daten|docker compose start|" ]'
ok "Umschalten: Rechte des Datenbankordners" '[ "$(stat -c %a "$T/i/daten/.sqlite")" = 700 ] && [ "$(stat -c %a "$T/i/daten/.sqlite/store.sqlite")" = 600 ]'
lauf rollback
ok "Rückfall bei aktivem SQLite: läuft durch" '[ $CODE = 0 ] && grep -q "datenbank rollback daten --offline" "$T/aufrufe" && [ ! -f "$T/i/daten/.sqlite-active" ]'

neu; touch "$T/fehler"
lauf migrate
ok "Fehler der Übernahme: Hinweis, App bleibt gestoppt (kein Start)" '[ $CODE = 1 ] && echo "$AUS" | grep -q "bleibt absichtlich gestoppt" && grep -q "compose stop" "$T/aufrufe" && ! grep -q "compose start" "$T/aufrufe"'
rm "$T/fehler"

lauf unsinn
ok "unbekannte Aktion abgelehnt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Aufruf:"'

echo "$PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
