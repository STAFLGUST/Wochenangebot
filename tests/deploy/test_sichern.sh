#!/bin/sh
# Test der Datensicherung (deploy/sichern.sh) in einem Wegwerf-Ordner mit Testdaten.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; fi; }
mkdir -p "$T/deploy"; cp "$REPO"/deploy/sichern.sh "$REPO"/deploy/sicherung-pruefen.* "$REPO"/deploy/datenbank.py "$REPO"/deploy/dateien_sichern.py "$T/deploy/"
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
# Dateiablage (hochgeladene Dokumente, nie in der Datenbank) wird auch im SQLite-Modus gesichert – als eigener Stand, nicht im Archiv
mkdir -p "$T/daten/dateien/qs/ab" "$T/daten/dateien/.teile"; echo PDF-Inhalt > "$T/daten/dateien/qs/ab/ab1234567890ab.bin"; echo halb > "$T/daten/dateien/.teile/x.part"; sleep 1
sh "$T/deploy/sichern.sh" --jetzt >/dev/null
LATEST=$(ls -1t "$T"/sicherungen/daten-*.tar.gz | head -1); STAND=$(basename "$LATEST" .tar.gz); STAND=${STAND#daten-}
ok "SQLite: Dateiablage als Stand gesichert (ohne halbe Uploads), nicht im Archiv" '[ "$(st ok)" = True ] && cmp -s "$T/sicherungen/dateien-daten/$STAND/qs/ab/ab1234567890ab.bin" "$T/daten/dateien/qs/ab/ab1234567890ab.bin" \
  && [ ! -e "$T/sicherungen/dateien-daten/$STAND/.teile" ] && ! tar tzf "$LATEST" | grep -q "dateien/"'
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
# ── Dateiablage: je Lauf ein Stand mit festen Verweisen auf den vorigen, geprüft gegen die Verweise der gesicherten Daten ──
W=$(mktemp -d); export W
mkdir -p "$W/deploy"; cp "$REPO"/deploy/sichern.sh "$REPO"/deploy/sicherung-pruefen.* "$REPO"/deploy/datenbank.py "$REPO"/deploy/dateien_sichern.py "$W/deploy/"
cp -r "$REPO/tests/fixtures/data-seed" "$W/daten"
sw() { python3 -c "import json; t=open('$W/daten/sicherung.php').read(); print(json.loads(t[t.index(chr(10))+1:]).get('$1'))"; }
# ablage <id> <inhalt>: Datei in die Ablage; verweise [zusatz-id]: qs-dokumente verweist (wie das QM-System) auf alle Dateien
ablage() { mkdir -p "$W/daten/dateien/qs/$(echo "$1" | cut -c1-2)"; printf '%s' "$2" > "$W/daten/dateien/qs/$(echo "$1" | cut -c1-2)/$1.bin"; }
verweise() { python3 - "$W/daten" "${1:-}" <<'PY'
import glob, hashlib, json, os, sys
d, extra = sys.argv[1], sys.argv[2]
f = [{'id': os.path.basename(p)[:-4], 'name': 'Datei.pdf', 'groesse': os.path.getsize(p), 'sha256': hashlib.sha256(open(p, 'rb').read()).hexdigest()}
     for p in sorted(glob.glob(d + '/dateien/qs/*/*.bin')) if not os.path.islink(p)]
if extra:
    f.append({'id': extra, 'name': 'fehlt.pdf', 'groesse': 3, 'sha256': '0' * 64})
open(d + '/qs-dokumente.php', 'w').write('<?php http_response_code(404); exit; ?>\n' + json.dumps({'liste': [{'id': 'd1', 'dateien': f}]}))
PY
}
stand() { ls -1d "$W"/sicherungen/dateien-daten/2* | sed -n "${1}p"; }
ablage aa00000000000000000001 'Inhalt eins'; ablage ab00000000000000000002 'Inhalt zwei'; ablage ac00000000000000000003 'Inhalt drei'
mkdir -p "$W/daten/dateien/.teile"; echo halb > "$W/daten/dateien/.teile/x.tmp"; ln -s /etc/hostname "$W/daten/dateien/qs/aa/ad00000000000000000004.bin"
verweise
sh "$W/deploy/sichern.sh" --jetzt >/dev/null
S1=$(stand 1); export S1
ok "Dateiablage: erster Stand mit allen Dateien, ohne halbe Uploads und Verweise, Archiv ohne dateien/" '[ "$(sw ok)" = True ] && [ "$(find "$S1" -type f | wc -l)" = 3 ] \
  && cmp -s "$S1/qs/ab/ab00000000000000000002.bin" "$W/daten/dateien/qs/ab/ab00000000000000000002.bin" && [ ! -e "$S1/.teile" ] && [ -z "$(find "$S1" -type l)" ] \
  && ! tar tzf "$W"/sicherungen/daten-*.tar.gz | grep -q "dateien/"'
ok "Dateiablage: Status nennt Anzahl, Größe, neu kopiert und Stände" '[ "$(sw dateien_anzahl)" = 3 ] && [ "$(sw dateien_groesse)" = 33 ] && [ "$(sw dateien_neu)" = 33 ] \
  && [ "$(sw dateien_staende)" = 1 ] && [ "$(sw dateien_belegt)" = 33 ] && [ "$(stat -c %a "$S1")" = 700 ]'
rm -r "$W/daten/dateien/qs/ac"; ablage ae00000000000000000005 'neue Datei'; verweise; sleep 1
sh "$W/deploy/sichern.sh" --jetzt >/dev/null
S2=$(stand 2); export S2
ok "Dateiablage: zweiter Stand verweist auf unveränderte Dateien, kopiert nur die neue, gelöschte bleibt im ersten" '[ "$(sw ok)" = True ] \
  && [ "$(stat -c %i "$S1/qs/aa/aa00000000000000000001.bin")" = "$(stat -c %i "$S2/qs/aa/aa00000000000000000001.bin")" ] \
  && [ -f "$S2/qs/ae/ae00000000000000000005.bin" ] && [ ! -e "$S2/qs/ac/ac00000000000000000003.bin" ] && [ -f "$S1/qs/ac/ac00000000000000000003.bin" ] \
  && [ "$(sw dateien_neu)" = 10 ] && [ "$(sw dateien_anzahl)" = 3 ] && [ "$(sw dateien_staende)" = 2 ] && [ "$(sw dateien_belegt)" = 43 ]'
verweise af00000000000000000006; sleep 1
sh "$W/deploy/sichern.sh" --jetzt >/dev/null 2>&1 || true
ok "Dateiablage: Verweis auf fehlende Datei → Fehler mit Meldung, kein neuer Stand" '[ "$(sw ok)" = False ] && grep -q "1 Datei(en), auf die die Daten verweisen, fehlen" "$W/daten/sicherung.php" \
  && [ "$(ls -1d "$W"/sicherungen/dateien-daten/2* | grep -vc "\.tmp$")" = 2 ]'
verweise
python3 -c "import os, sys; p = sys.argv[1]; t = os.stat(p); open(p, 'r+b').write(b'X'); os.utime(p, ns=(t.st_atime_ns, t.st_mtime_ns))" "$S2/qs/ab/ab00000000000000000002.bin"; sleep 1
sh "$W/deploy/sichern.sh" --jetzt >/dev/null 2>&1 || true
ok "Dateiablage: veränderte Kopie in der Sicherung fällt bei der Stichprobe mit SHA-256 auf" '[ "$(sw ok)" = False ] && grep -q "Prüfsumme in der Dateisicherung stimmt nicht" "$W/daten/sicherung.php" \
  && [ -z "$(ls -d "$W"/sicherungen/dateien-daten/*.tmp 2>/dev/null)" ] || [ "$(ls -d "$W"/sicherungen/dateien-daten/*.tmp | wc -l)" = 1 ]'
rm -rf "$W"/sicherungen/dateien-daten; sleep 1
sh "$W/deploy/sichern.sh" --jetzt >/dev/null
ok "Dateiablage: nach dem Entfernen der kaputten Stände wieder vollständig kopiert, Rest des Fehllaufs aufgeräumt" '[ "$(sw ok)" = True ] && [ "$(sw dateien_neu)" = 32 ] \
  && [ -z "$(ls -d "$W"/sicherungen/dateien-daten/*.tmp 2>/dev/null)" ]'
LATEST=$(ls -1t "$W"/sicherungen/daten-*.tar.gz | head -1); STAND=$(basename "$LATEST" .tar.gz); STAND=${STAND#daten-}
mkdir "$W/zurueck"; tar xzf "$LATEST" -C "$W/zurueck"; cp -a "$W/sicherungen/dateien-daten/$STAND" "$W/zurueck/dateien"
ok "Wiederherstellung: Archiv und Stand derselben Zeit ergeben Daten und Dateiablage (ohne halbe Uploads)" 'diff -r -x .teile -x ad00000000000000000004.bin "$W/daten/dateien" "$W/zurueck/dateien" >/dev/null \
  && cmp -s "$W/daten/qs-dokumente.php" "$W/zurueck/qs-dokumente.php" && [ "$(stat -c %h "$W/zurueck/dateien/qs/aa/aa00000000000000000001.bin")" = 1 ]'
for Z in 2099-01-01_000000 2099-01-02_000000; do
  python3 "$W/deploy/dateien_sichern.py" aufbauen "$W/daten/dateien" "$W/sicherungen/dateien-daten" "$Z" >/dev/null
  python3 "$W/deploy/dateien_sichern.py" abschliessen 2 "$Z" "$W/sicherungen/dateien-daten" --daten "$W/daten" >/dev/null
done
ok "Aufbewahrung: nur die neuesten Stände bleiben, ihre Dateien vollständig" '[ "$(ls -1 "$W"/sicherungen/dateien-daten | tr "\n" " ")" = "2099-01-01_000000 2099-01-02_000000 " ] \
  && [ "$(find "$W/sicherungen/dateien-daten/2099-01-02_000000" -type f | wc -l)" = 3 ] && [ "$(find "$W/sicherungen/dateien-daten/2099-01-01_000000" -type f | wc -l)" = 3 ]'
mkdir "$W/bin"; printf '#!/bin/sh\necho "Filesystem 1024-blocks Used Available Capacity Mounted"\necho "/dev/x 400000000 399000000 1048576 99%% /"\n' > "$W/bin/df"; chmod +x "$W/bin/df"
ablage ag00000000000000000007 'noch eine'; verweise; sleep 1
ANZ_VOR=$(ls "$W"/sicherungen/daten-*.tar.gz | wc -l); export ANZ_VOR
PATH="$W/bin:$PATH" sh "$W/deploy/sichern.sh" --jetzt >/dev/null 2>&1 || true
ok "zu wenig Platz (1 GB frei): Abbruch vor dem Sichern mit Meldung im Status" '[ "$(sw ok)" = False ] && grep -q "zu wenig Speicherplatz: 1,0 GB frei, nötig 5,0 GB" "$W/daten/sicherung.php" \
  && [ "$(ls "$W"/sicherungen/daten-*.tar.gz | wc -l)" = "$ANZ_VOR" ]'
rm "$W/deploy/dateien_sichern.py"; sleep 1
sh "$W/deploy/sichern.sh" --jetzt >/dev/null
LATEST=$(ls -1t "$W"/sicherungen/daten-*.tar.gz | head -1); export LATEST
ok "ohne Werkzeug (Sicherung vor dem Release mit altem deploy/): Dateiablage wie bisher im Archiv" '[ "$(sw ok)" = True ] && tar tzf "$LATEST" | grep -q "dateien/qs/ag/ag00000000000000000007.bin" \
  && ! tar tzf "$LATEST" | grep -q "x.tmp"'
chmod -R u+rwx "$W" 2>/dev/null; rm -rf "$W"
# Getrennte Daten (ADR-007 Stufe 2): zweites Archiv intern-*.tar.gz für daten-intern/, gleich geprüft – Dateien und SQLite
for ART in dateien sqlite; do
  U=$(mktemp -d)
  mkdir -p "$U/deploy" "$U/regeln"; cp "$REPO"/deploy/sichern.sh "$REPO"/deploy/sicherung-pruefen.* "$REPO"/deploy/datenbank.py "$REPO"/deploy/daten_trennen.py "$REPO"/deploy/dateien_sichern.py "$U/deploy/"
  cp "$REPO/regeln/datenverantwortung.toml" "$U/regeln/"; cp -r "$REPO/tests/fixtures/data-seed" "$U/daten"
  printf '%s\n{"personen":[{"name":"Test Person"}]}' '<?php http_response_code(404); exit; ?>' > "$U/daten/hr-personal.php"
  mkdir -p "$U/daten/dateien/qs/ba"; printf 'Prüfbericht' > "$U/daten/dateien/qs/ba/ba00000000000000000001.bin"
  printf '%s\n{"liste":[{"id":"d1","dateien":[{"id":"ba00000000000000000001","groesse":12,"sha256":"%s"}]}]}' '<?php http_response_code(404); exit; ?>' \
    "$(sha256sum "$U/daten/dateien/qs/ba/ba00000000000000000001.bin" | cut -c1-64)" > "$U/daten/qs-dokumente.php"
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
  ok "getrennt ($ART): Dateiablage aus daten-intern als Stand dateien-intern, gegen das interne Archiv geprüft" '[ "$(su dateien_anzahl)" = 1 ] \
    && [ -f "$U/sicherungen/dateien-intern/$(basename "$U"/sicherungen/intern-*.tar.gz .tar.gz | cut -c8-)/qs/ba/ba00000000000000000001.bin" ] && [ ! -e "$U/sicherungen/dateien-daten" ]'
  ok "getrennt ($ART): Datensätze beider Bereiche gezählt" '[ "$(su datensaetze)" -ge 2 ] && [ "$(stat -c %a "$U"/sicherungen/intern-*.tar.gz)" = 600 ]'
  rm -f "$U/daten/.daten-getrennt"; sleep 1
  sh "$U/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?
  ok "getrennt ($ART): Kennzeichen in daten/ entfernt → Fehler statt Sicherung ohne interne Daten" '[ "$R" = 1 ] && [ "$(su ok)" = False ] \
    && grep -q "Kennzeichen" "$U/daten/sicherung.php" && [ "$(ls "$U"/sicherungen/intern-*.tar.gz | wc -l)" = 1 ]'
  printf '%s\n' "$(cat "$U/daten-intern/.daten-intern")" > "$U/daten/.daten-getrennt"
  mv "$U/daten-intern" "$U/weg"; sleep 1
  sh "$U/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?
  ok "getrennt ($ART): daten-intern fehlt → Fehler statt Sicherung ohne interne Daten" '[ "$R" = 1 ] && [ "$(su ok)" = False ] && grep -q "daten-intern" "$U/daten/sicherung.php"'
  chmod -R u+rwx "$U" 2>/dev/null; rm -rf "$U"
done
echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" -eq 0 ]
