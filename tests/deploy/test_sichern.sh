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
ok "Status nennt Datensätze und Speicherart (Dateien)" '[ "$(st speicher)" = dateien ] && [ "$(st datensaetze)" -ge 1 ]'
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
ok "Status nennt Datensätze und Speicherart (Datenbank)" '[ "$(st speicher)" = sqlite ] && [ "$(st datensaetze)" -ge 1 ]'
LATEST=$(ls -1t "$T"/sicherungen/daten-*.tar.gz | head -1)
mkdir "$T/restore"
tar xzf "$LATEST" -C "$T/restore"
ok "SQLite-Archiv enthält geprüfte Datenbank" 'python3 "$T/deploy/datenbank.py" check "$T/restore" >/dev/null'
ok "SQLite-Archiv enthält keinen Postfachschlüssel" '[ ! -f "$T/restore/mail-schluessel.php" ]'
# Dateiablage (hochgeladene Dokumente, nie in der Datenbank) gehört auch im SQLite-Modus in die Sicherung; halbe Uploads nicht
mkdir -p "$T/daten/dateien/qs/ab" "$T/daten/dateien/.teile"; echo PDF-Inhalt > "$T/daten/dateien/qs/ab/ab12.bin"; echo halb > "$T/daten/dateien/.teile/x.part"; sleep 1
sh "$T/deploy/sichern.sh" --jetzt >/dev/null
LATEST=$(ls -1t "$T"/sicherungen/daten-*.tar.gz | head -1)
ok "SQLite-Archiv enthält die Dateiablage (ohne halbe Uploads)" 'tar tzf "$LATEST" | grep -q "dateien/qs/ab/ab12.bin" && ! tar tzf "$LATEST" | grep -q "x.part"'
rm -rf "$T/daten/dateien"
printf 'broken' > "$T/restore/.sqlite/store.sqlite"
ok "Beschädigte Datenbank im Archiv erkannt" '[ "$(python3 "$T/deploy/sicherung-pruefen.py" "$T/restore")" -gt 0 ]'
ok "ohne zentrale Anmeldung: keine Keycloak-Sicherung, Status aus" '[ "$(st anmeldung)" = aus ] && ! ls "$T"/sicherungen/anmeldung-* >/dev/null 2>&1'
# daten/ ist im Container beschreibbar: dort angelegte Verweise dürfen den Status (root) nie auf andere Dateien umlenken
echo ORIGINAL > "$T/opfer"; chmod 600 "$T/opfer"; rm -f "$T/daten/sicherung.php"
ln -s "$T/opfer" "$T/daten/sicherung.php"; ln -s "$T/opfer2" "$T/daten/sicherung.php.tmp"
sleep 1; sh "$T/deploy/sichern.sh" --jetzt >/dev/null
ok "Status folgt keinem Verweis in daten/ (Ziel unverändert, Verweis ersetzt)" '[ "$(cat "$T/opfer")" = ORIGINAL ] && [ "$(stat -c %a "$T/opfer")" = 600 ] && [ ! -e "$T/opfer2" ] \
  && [ ! -L "$T/daten/sicherung.php" ] && [ "$(st ok)" = True ] && [ -z "$(ls -A "$T" | grep "^\.status\.")" ]'
rm -f "$T/daten/sicherung.php.tmp"

# ── Zentrale Anmeldung: Keycloak-Datenbank (echte PostgreSQL-Instanz statt Container; Ersatz für „docker compose“) ──
PGBIN=$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)
if [ -z "$PGBIN" ]; then
  echo "HINWEIS: keine PostgreSQL-Programme – Prüfungen der Keycloak-Sicherung übersprungen"
else
  als() { if [ "$(id -u)" = 0 ]; then runuser -u postgres -- "$@"; else "$@"; fi; }
  PG=$(mktemp -d); chmod 755 "$PG"; mkdir "$PG/daten" "$PG/sock"
  [ "$(id -u)" = 0 ] && chown postgres "$PG/daten" "$PG/sock"
  PGPORT=$((20000 + $$ % 10000))
  # wie im Container (POSTGRES_INITDB_ARGS --auth=scram-sha-256): Passwortpflicht auch über den lokalen Socket
  export KC_PW; KC_PW="test-$(date +%s)"; printf '%s\n' "$KC_PW" > "$PG/sock/pw"; [ "$(id -u)" = 0 ] && chown postgres "$PG/sock/pw"
  als "$PGBIN/initdb" -D "$PG/daten" --auth=scram-sha-256 --pwfile="$PG/sock/pw" -U keycloak >/dev/null; rm -f "$PG/sock/pw"
  als "$PGBIN/pg_ctl" -D "$PG/daten" -l "$PG/sock/log" -o "-p $PGPORT -k $PG/sock -c listen_addresses=" -w start >/dev/null
  trap 'als "$PGBIN/pg_ctl" -D "$PG/daten" -m fast stop >/dev/null 2>&1; rm -rf "$PG"; chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"' EXIT
  export PGHOST="$PG/sock" PGPORT PGBIN
  pgx() { p=$1; shift; PGPASSWORD="$KC_PW" "$PGBIN/$p" "$@"; }
  ok "Testdatenbank verlangt ein Passwort (wie im Container)" '! "$PGBIN/psql" -w -U keycloak -d postgres -c "select 1" >/dev/null 2>&1'
  pgx createdb -U keycloak keycloak
  pgx psql -U keycloak -d keycloak -q -c "CREATE TABLE user_entity (id text primary key, username text)" -c "INSERT INTO user_entity VALUES ('1', 'probe-konto')"
  # Ersatz für „docker compose -f … -f …“: ps -q keycloak-db / exec -T keycloak-db <Programm> …
  cat > "$T/compose.sh" <<'EOF2'
#!/bin/sh
case "$1" in
  ps) [ -f "$KC_LAEUFT" ] && echo 0123abcd; exit 0 ;;
  exec) shift; [ "$1" = -T ] && shift; shift; p=$1; shift
        # Umgebung des Containers: POSTGRES_PASSWORD gesetzt, PGPASSWORD nicht
        if [ "$p" = sh ]; then exec env -u PGPASSWORD POSTGRES_PASSWORD="$KC_PW" PATH="$PGBIN:$PATH" sh "$@"; fi
        exec env -u PGPASSWORD "$PGBIN/$p" "$@" ;;
esac
exit 1
EOF2
  export WA_KC_COMPOSE="sh $T/compose.sh" KC_LAEUFT="$T/kc-laeuft"
  mkdir -p "$T/deploy/anmeldung" "$T/daten-anmeldung"; touch "$T/deploy/anmeldung/docker-compose.anmeldung.yml"
  sleep 1
  sh "$T/deploy/sichern.sh" --jetzt >/dev/null
  ok "Anmeldung eingerichtet, Keycloak noch nicht gestartet: nicht gesichert, kein Fehler" '[ "$(st ok)" = True ] && [ "$(st anmeldung)" = aus ]'
  touch "$KC_LAEUFT"; sleep 1
  export AUS; AUS=$(sh "$T/deploy/sichern.sh" --jetzt) || true
  DUMP=$(ls -1t "$T"/sicherungen/anmeldung-*.dump 2>/dev/null | head -1)
  ok "Keycloak läuft: Datenbank gesichert und geprüft" '[ "$(st ok)" = True ] && [ "$(st anmeldung)" = ok ] && [ -n "$DUMP" ] && [ "$(st anmeldung_datei)" = "$(basename "$DUMP")" ]'
  ok "Keycloak-Sicherung nur für root lesbar, Meldung nennt sie" '[ "$(stat -c %a "$DUMP")" = 600 ] && echo "$AUS" | grep -q "Anmeldung: anmeldung-"'
  pgx createdb -U keycloak rueck
  pgx pg_restore -U keycloak -d rueck --no-owner "$DUMP"
  ok "Rücksicherung: Konten wieder da" '[ "$(PGPASSWORD="$KC_PW" "$PGBIN/psql" -U keycloak -d rueck -tAc "SELECT username FROM user_entity")" = probe-konto ]'
  cp "$REPO/deploy/anmeldung/ruecksicherung-probe.sh" "$T/deploy/anmeldung/"
  export PROBE; PROBE=$(cd "$T" && sh deploy/anmeldung/ruecksicherung-probe.sh 2>&1)
  ok "Rücksicherungsprobe: zählt die Konten, Probedatenbank danach gelöscht" 'echo "$PROBE" | grep -q "1 Konten" && [ -z "$(PGPASSWORD="$KC_PW" "$PGBIN/psql" -U keycloak -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '"'"'ruecksicherung_probe'"'"'")" ]'
  pgx psql -U keycloak -d keycloak -q -c "DROP TABLE user_entity"; sleep 1
  sh "$T/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?; export R
  ok "Keycloak-Sicherung ohne Konten wird als Fehler gemeldet (Geschäftsdaten trotzdem gesichert)" '[ "$R" = 1 ] && [ "$(st ok)" = False ] && [ "$(st anmeldung)" = fehler ] && grep -q "Anmeldung (Keycloak) fehlgeschlagen" "$T/daten/sicherung.php" && [ "$(ls "$T"/sicherungen/daten-*.tar.gz | wc -l)" -ge 4 ]'
  ok "keine halbfertige Keycloak-Sicherung liegen gelassen" '! ls "$T"/sicherungen/anmeldung-*.tmp >/dev/null 2>&1 && [ "$(ls "$T"/sicherungen/anmeldung-*.dump | wc -l)" = 1 ]'
  pgx psql -U keycloak -d keycloak -q -c "CREATE TABLE user_entity (id text primary key, username text)" -c "INSERT INTO user_entity VALUES ('1', 'probe-konto')"
  ECHT_PW=$KC_PW; KC_PW=falsch; sleep 1
  sh "$T/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?; export R
  ok "falsches Datenbankpasswort: Fehler mit Grund in der Meldung, Status gültig" '[ "$R" = 1 ] && grep -q "Keycloak) fehlgeschlagen: .*password authentication failed" "$T/daten/sicherung.php" && [ "$(st anmeldung)" = fehler ]'
  KC_PW=$ECHT_PW
  rm "$KC_LAEUFT"; printf 'COMPOSE_FILE=docker-compose.yml:deploy/anmeldung/docker-compose.anmeldung.yml\n' > "$T/.env"; sleep 1
  sh "$T/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?; export R
  ok "Anmeldung in Betrieb, Datenbank läuft nicht: Fehler statt stiller Lücke" '[ "$R" = 1 ] && [ "$(st anmeldung)" = fehler ] && grep -q "Datenbank läuft aber nicht" "$T/daten/sicherung.php"'
fi
# Getrennte Daten (ADR-007 Stufe 2): zweites Archiv intern-*.tar.gz für daten-intern/, gleich geprüft – Dateien und SQLite
for ART in dateien sqlite; do
  U=$(mktemp -d)
  mkdir -p "$U/deploy" "$U/regeln"; cp "$REPO"/deploy/sichern.sh "$REPO"/deploy/sicherung-pruefen.* "$REPO"/deploy/datenbank.py "$REPO"/deploy/daten_trennen.py "$U/deploy/"
  cp "$REPO/regeln/datenverantwortung.toml" "$U/regeln/"; cp -r "$REPO/tests/fixtures/data-seed" "$U/daten"
  printf '%s\n{"personen":[{"name":"Test Person"}]}' '<?php http_response_code(404); exit; ?>' > "$U/daten/hr-personal.php"
  [ "$ART" = sqlite ] && python3 "$U/deploy/datenbank.py" migrate "$U/daten" --offline >/dev/null
  python3 "$U/deploy/daten_trennen.py" trennen "$U/daten" "$U/daten-intern" --offline >/dev/null
  sh "$U/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?; export R U
  su() { python3 -c "import json; t=open('$U/daten/sicherung.php').read(); print(json.loads(t[t.index(chr(10))+1:]).get('$1'))"; }
  ok "getrennt ($ART): zwei Archive, beide geprüft" '[ "$R" = 0 ] && [ "$(su ok)" = True ] && [ "$(ls "$U"/sicherungen/daten-*.tar.gz | wc -l)" = 1 ] && [ "$(ls "$U"/sicherungen/intern-*.tar.gz | wc -l)" = 1 ] && [ "$(su intern_datei)" = "$(basename "$U"/sicherungen/intern-*.tar.gz)" ]'
  mkdir "$U/r1" "$U/r2"; tar xzf "$U"/sicherungen/daten-*.tar.gz -C "$U/r1"; tar xzf "$U"/sicherungen/intern-*.tar.gz -C "$U/r2"
  if [ "$ART" = dateien ]; then
    ok "getrennt ($ART): Personaldaten nur im internen Archiv" '[ -f "$U/r2/hr-personal.php" ] && [ ! -e "$U/r1/hr-personal.php" ] && [ -f "$U/r1/angebot.php" ] && [ -f "$U/r2/.daten-intern" ] && [ -f "$U/r1/.daten-getrennt" ]'
  else
    ok "getrennt ($ART): Personaldaten nur in der internen Datenbank" 'python3 -c "import sqlite3,sys; a=sqlite3.connect(sys.argv[1]); b=sqlite3.connect(sys.argv[2]); n=lambda c: {r[0] for r in c.execute(\"SELECT name FROM documents\")}; sys.exit(0 if \"hr-personal\" in n(b) and \"hr-personal\" not in n(a) and \"angebot\" in n(a) else 1)" "$U/r1/.sqlite/store.sqlite" "$U/r2/.sqlite/store.sqlite"'
  fi
  ok "getrennt ($ART): Datensätze beider Bereiche gezählt" '[ "$(su datensaetze)" -ge 2 ] && [ "$(stat -c %a "$U"/sicherungen/intern-*.tar.gz)" = 600 ]'
  mv "$U/daten-intern" "$U/weg"; sleep 1
  sh "$U/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?
  ok "getrennt ($ART): daten-intern fehlt → Fehler statt Sicherung ohne interne Daten" '[ "$R" = 1 ] && [ "$(su ok)" = False ] && grep -q "daten-intern" "$U/daten/sicherung.php"'
  chmod -R u+rwx "$U" 2>/dev/null; rm -rf "$U"
done
echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" -eq 0 ]
