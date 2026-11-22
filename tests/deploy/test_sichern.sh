#!/bin/sh
# Test der Datensicherung (deploy/sichern.sh) in einem Wegwerf-Ordner mit Testdaten.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"' EXIT   # alle Arbeitsordner liegen unter $T
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; fi; }
mkdir -p "$T/deploy"; cp "$REPO"/deploy/sichern.sh "$REPO"/deploy/sicherung-pruefen.* "$REPO"/deploy/datenbank.py "$REPO"/deploy/dateien_sichern.py "$T/deploy/"
cp -r "$REPO/tests/fixtures/data-seed" "$T/daten"
printf '%s\n{"key":"dGVzdA=="}' '<?php http_response_code(404); exit; ?>' > "$T/daten/mail-schluessel.php"
# feld <datenordner> <schlüssel[.unterschlüssel]>: Wert aus dem Status der Sicherung (sicherung.php)
feld() { python3 -c "import functools, json, sys; t = open(sys.argv[1] + '/sicherung.php').read(); print(functools.reduce(lambda v, k: (v or {}).get(k), sys.argv[2].split('.'), json.loads(t[t.index(chr(10)) + 1:])))" "$1" "$2"; }

sh "$T/deploy/sichern.sh" >/dev/null
ok "Sicherung erstellt und geprüft" '[ "$(feld "$T/daten" ok)" = True ] && [ "$(feld "$T/daten" inhalt)" = True ] && [ "$(ls "$T"/sicherungen/daten-*.tar.gz | wc -l)" -eq 1 ]'
ok "Status nennt Datensätze und Speicherart (Dateien)" '[ "$(feld "$T/daten" speicher)" = dateien ] && [ "$(feld "$T/daten" datensaetze)" -ge 1 ]'
ok "Archiv nur für root lesbar" '[ "$(stat -c %a "$T/sicherungen")" = 700 ] && [ "$(stat -c %a "$T"/sicherungen/daten-*.tar.gz)" = 600 ]'
ok "Archiv enthält die Daten" 'tar tzf "$T"/sicherungen/daten-*.tar.gz | grep -q angebot.php'
ok "Schlüssel für das Postfach-Passwort wird nicht gesichert" '! tar tzf "$T"/sicherungen/daten-*.tar.gz | grep -q mail-schluessel'
sh "$T/deploy/sichern.sh" >/dev/null
ok "innerhalb von 23 Stunden keine zweite Sicherung" '[ "$(ls "$T"/sicherungen/daten-*.tar.gz | wc -l)" -eq 1 ]'
echo '{kaputt' > "$T/daten/defekt.php"; sleep 1
sh "$T/deploy/sichern.sh" --jetzt >/dev/null || true
ok "defekte Datei wird erkannt, kein Archiv und kein .tmp dieses Laufs" '[ "$(feld "$T/daten" ok)" = False ] && [ "$(feld "$T/daten" fehler)" = 1 ] && [ "$(ls "$T"/sicherungen/daten-*.tar.gz | wc -l)" -eq 1 ] \
  && [ -z "$(find "$T/sicherungen" -name "*.tmp")" ]'
rm "$T/daten/defekt.php"
mv "$T/sicherungen" "$T/s2"; touch "$T/sicherungen"   # Ablage nicht anlegbar → unerwarteter Abbruch
sh "$T/deploy/sichern.sh" --jetzt >/dev/null 2>&1 || true
ok "unerwarteter Abbruch hinterlässt Fehlerstatus" '[ "$(feld "$T/daten" ok)" = False ] && grep -q "Abbruch" "$T/daten/sicherung.php"'
rm "$T/sicherungen"; mv "$T/s2" "$T/sicherungen"
# Database backup must use a snapshot and verify its actual contents.
python3 "$T/deploy/datenbank.py" migrate "$T/daten" --offline >/dev/null
sleep 1
sh "$T/deploy/sichern.sh" --jetzt >/dev/null
ok "SQLite-Sicherung erstellt und geprüft" '[ "$(feld "$T/daten" ok)" = True ] && [ "$(feld "$T/daten" inhalt)" = True ]'
ok "Status nennt Datensätze und Speicherart (Datenbank)" '[ "$(feld "$T/daten" speicher)" = sqlite ] && [ "$(feld "$T/daten" datensaetze)" -ge 1 ]'
LATEST=$(ls -1t "$T"/sicherungen/daten-*.tar.gz | head -1)
mkdir "$T/restore"
tar xzf "$LATEST" -C "$T/restore"
ok "SQLite-Archiv enthält geprüfte Datenbank" 'python3 "$T/deploy/datenbank.py" check "$T/restore" >/dev/null'
ok "SQLite-Archiv enthält keinen Postfachschlüssel" '[ ! -f "$T/restore/mail-schluessel.php" ]'
# Dateiablage (hochgeladene Dokumente, nie in der Datenbank) wird auch im SQLite-Modus gesichert – als eigener Stand, nicht im Archiv
mkdir -p "$T/daten/dateien/qs/ab" "$T/daten/dateien/.teile"; echo PDF-Inhalt > "$T/daten/dateien/qs/ab/ab1234567890ab.bin"; echo halb > "$T/daten/dateien/.teile/x.part"; sleep 1
# tar-Attrappe merkt sich, ob der Abzug der Datenbank (Quelle des Archivs) die Dateiablage enthält (je Lauf 12 GB nach /tmp)
mkdir "$T/bin-abzug"; ECHT_TAR=$(command -v tar); export ECHT_TAR T
printf '#!/bin/sh\n[ "$1" != czf ] || [ ! -d "$4/dateien" ] || echo "$4" >> "$T/abzug-mit-dateien"\nexec "$ECHT_TAR" "$@"\n' > "$T/bin-abzug/tar"; chmod +x "$T/bin-abzug/tar"
PATH="$T/bin-abzug:$PATH" sh "$T/deploy/sichern.sh" --jetzt >/dev/null
LATEST=$(ls -1t "$T"/sicherungen/daten-*.tar.gz | head -1); STAND=$(basename "$LATEST" .tar.gz); STAND=${STAND#daten-}
ok "SQLite: Dateiablage als Stand gesichert (ohne halbe Uploads), weder im Archiv noch im Abzug der Datenbank" '[ "$(feld "$T/daten" ok)" = True ] && cmp -s "$T/sicherungen/dateien/$STAND/qs/ab/ab1234567890ab.bin" "$T/daten/dateien/qs/ab/ab1234567890ab.bin" \
  && [ ! -e "$T/sicherungen/dateien/$STAND/.teile" ] && ! tar tzf "$LATEST" | grep -q "dateien/" && [ ! -e "$T/abzug-mit-dateien" ]'
ok "Datenbank-Abzug: ohne Schalter mit Dateiablage (älteres sichern.sh), mit WA_SNAPSHOT_OHNE_DATEIEN=1 ohne" 'python3 "$T/deploy/datenbank.py" snapshot "$T/daten" --output "$T/abzug1" >/dev/null \
  && cmp -s "$T/abzug1/dateien/qs/ab/ab1234567890ab.bin" "$T/daten/dateien/qs/ab/ab1234567890ab.bin" && [ ! -e "$T/abzug1/dateien/.teile" ] \
  && WA_SNAPSHOT_OHNE_DATEIEN=1 python3 "$T/deploy/datenbank.py" snapshot "$T/daten" --output "$T/abzug2" >/dev/null && [ ! -e "$T/abzug2/dateien" ]'
mv "$T/deploy/dateien_sichern.py" "$T/werkzeug.py"; sleep 1
PATH="$T/bin-abzug:$PATH" sh "$T/deploy/sichern.sh" --jetzt >/dev/null
LATEST=$(ls -1t "$T"/sicherungen/daten-*.tar.gz | head -1)
ok "SQLite ohne Werkzeug: Dateiablage über den Abzug im Archiv statt stiller Lücke" '[ "$(feld "$T/daten" ok)" = True ] && tar tzf "$LATEST" | grep -q "dateien/qs/ab/ab1234567890ab.bin" && ! tar tzf "$LATEST" | grep -q "x.part" \
  && [ -s "$T/abzug-mit-dateien" ]'
mv "$T/werkzeug.py" "$T/deploy/dateien_sichern.py"
rm -rf "$T/daten/dateien"
printf 'broken' > "$T/restore/.sqlite/store.sqlite"
ok "Beschädigte Datenbank im Archiv erkannt" '[ "$(python3 "$T/deploy/sicherung-pruefen.py" "$T/restore")" -gt 0 ]'
ok "ohne zentrale Anmeldung: keine Keycloak-Sicherung, Status aus" '[ "$(feld "$T/daten" anmeldung)" = aus ] && ! ls "$T"/sicherungen/anmeldung-* >/dev/null 2>&1'
# daten/ ist im Container beschreibbar: dort angelegte Verweise dürfen den Status (root) nie auf andere Dateien umlenken
echo ORIGINAL > "$T/opfer"; chmod 600 "$T/opfer"; rm -f "$T/daten/sicherung.php"
ln -s "$T/opfer" "$T/daten/sicherung.php"; ln -s "$T/opfer2" "$T/daten/sicherung.php.tmp"
sleep 1; sh "$T/deploy/sichern.sh" --jetzt >/dev/null
ok "Status folgt keinem Verweis in daten/ (Ziel unverändert, Verweis ersetzt)" '[ "$(cat "$T/opfer")" = ORIGINAL ] && [ "$(stat -c %a "$T/opfer")" = 600 ] && [ ! -e "$T/opfer2" ] \
  && [ ! -L "$T/daten/sicherung.php" ] && [ "$(feld "$T/daten" ok)" = True ] && [ -z "$(ls -A "$T" | grep "^\.status\.")" ]'
rm -f "$T/daten/sicherung.php.tmp"
# SQLite-Abzug: ein unter index.php bzw. .daten-intern (ohne Datentrennung) in daten/ angelegter Verweis trägt nie eine Datei des
# Wirts ins Archiv – auch nicht still bei grünem Status
echo ERFUNDENES-WIRTSGEHEIMNIS-NUR-TEST > "$T/wirt-geheim"; chmod 600 "$T/wirt-geheim"; mv "$T/daten/index.php" "$T/index.php.echt"
ln -s "$T/wirt-geheim" "$T/daten/index.php"; ln -s "$T/wirt-geheim" "$T/daten/.daten-intern"
sleep 1; sh "$T/deploy/sichern.sh" --jetzt >/dev/null
LATEST=$(ls -1t "$T"/sicherungen/daten-*.tar.gz | head -1)
ok "SQLite-Abzug folgt keinem Verweis in daten/: Wirtsdatei nicht im Archiv" '[ "$(feld "$T/daten" ok)" = True ] && ! zcat "$LATEST" | grep -aq ERFUNDENES-WIRTSGEHEIMNIS && ! tar tzf "$LATEST" | grep -Eq "^\./(index\.php|\.daten-intern)$"'
rm -f "$T/daten/index.php" "$T/daten/.daten-intern"; mv "$T/index.php.echt" "$T/daten/index.php"

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
  ok "Anmeldung eingerichtet, Keycloak noch nicht gestartet: nicht gesichert, kein Fehler" '[ "$(feld "$T/daten" ok)" = True ] && [ "$(feld "$T/daten" anmeldung)" = aus ]'
  touch "$KC_LAEUFT"; sleep 1
  export AUS; AUS=$(sh "$T/deploy/sichern.sh" --jetzt) || true
  DUMP=$(ls -1t "$T"/sicherungen/anmeldung-*.dump 2>/dev/null | head -1)
  ok "Keycloak läuft: Datenbank gesichert und geprüft" '[ "$(feld "$T/daten" ok)" = True ] && [ "$(feld "$T/daten" anmeldung)" = ok ] && [ -n "$DUMP" ] && [ "$(feld "$T/daten" anmeldung_datei)" = "$(basename "$DUMP")" ]'
  ok "Keycloak-Sicherung nur für root lesbar, Meldung nennt sie" '[ "$(stat -c %a "$DUMP")" = 600 ] && echo "$AUS" | grep -q "Anmeldung: anmeldung-"'
  pgx createdb -U keycloak rueck
  pgx pg_restore -U keycloak -d rueck --no-owner "$DUMP"
  ok "Rücksicherung: Konten wieder da" '[ "$(PGPASSWORD="$KC_PW" "$PGBIN/psql" -U keycloak -d rueck -tAc "SELECT username FROM user_entity")" = probe-konto ]'
  cp "$REPO/deploy/anmeldung/ruecksicherung-probe.sh" "$T/deploy/anmeldung/"
  export PROBE; PROBE=$(cd "$T" && sh deploy/anmeldung/ruecksicherung-probe.sh 2>&1)
  ok "Rücksicherungsprobe: zählt die Konten, Probedatenbank danach gelöscht" 'echo "$PROBE" | grep -q "1 Konten" && [ -z "$(PGPASSWORD="$KC_PW" "$PGBIN/psql" -U keycloak -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '"'"'ruecksicherung_probe'"'"'")" ]'
  pgx psql -U keycloak -d keycloak -q -c "DROP TABLE user_entity"; sleep 1
  sh "$T/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?; export R
  ok "Keycloak-Sicherung ohne Konten wird als Fehler gemeldet (Geschäftsdaten trotzdem gesichert)" '[ "$R" = 1 ] && [ "$(feld "$T/daten" ok)" = False ] && [ "$(feld "$T/daten" anmeldung)" = fehler ] && grep -q "Anmeldung (Keycloak) fehlgeschlagen" "$T/daten/sicherung.php" && [ "$(ls "$T"/sicherungen/daten-*.tar.gz | wc -l)" -ge 4 ]'
  ok "keine halbfertige Keycloak-Sicherung liegen gelassen" '! ls "$T"/sicherungen/anmeldung-*.tmp >/dev/null 2>&1 && [ "$(ls "$T"/sicherungen/anmeldung-*.dump | wc -l)" = 1 ]'
  pgx psql -U keycloak -d keycloak -q -c "CREATE TABLE user_entity (id text primary key, username text)" -c "INSERT INTO user_entity VALUES ('1', 'probe-konto')"
  ECHT_PW=$KC_PW; KC_PW=falsch; sleep 1
  sh "$T/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?; export R
  ok "falsches Datenbankpasswort: Fehler mit Grund in der Meldung, Status gültig" '[ "$R" = 1 ] && grep -q "Keycloak) fehlgeschlagen: .*password authentication failed" "$T/daten/sicherung.php" && [ "$(feld "$T/daten" anmeldung)" = fehler ]'
  KC_PW=$ECHT_PW
  rm "$KC_LAEUFT"; printf 'COMPOSE_FILE=docker-compose.yml:deploy/anmeldung/docker-compose.anmeldung.yml\n' > "$T/.env"; sleep 1
  sh "$T/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?; export R
  ok "Anmeldung in Betrieb, Datenbank läuft nicht: Fehler statt stiller Lücke" '[ "$R" = 1 ] && [ "$(feld "$T/daten" anmeldung)" = fehler ] && grep -q "Datenbank läuft aber nicht" "$T/daten/sicherung.php"'
fi
# ── Dateiablage: je Lauf ein Stand sicherungen/dateien/<Zeit>/ mit festen Verweisen auf den vorigen, geprüft gegen die Verweise ──
umgebung() { W=$1; export W; mkdir -p "$W/deploy"; cp "$REPO"/deploy/sichern.sh "$REPO"/deploy/sicherung-pruefen.* "$REPO"/deploy/datenbank.py "$REPO"/deploy/dateien_sichern.py "$W/deploy/"
  cp -r "$REPO/tests/fixtures/data-seed" "$W/daten"; }   # neuer Arbeitsordner $W mit Testdaten; die Helfer unten arbeiten in $W
umgebung "$T/w"; export T
# verweise.py <daten> [fehlt:<id>] [roh:<id>] [groesse:<id>:<bytes>]: qs-dokumente verweist (wie das QM-System) auf alle Dateien der
# Ablage; dazu ein Verweis auf eine fehlende Datei, eine Rohfassung {roh, sha256Roh} statt {id, groesse, sha256} bzw. eine andere Größe
cat > "$T/verweise.py" <<'PY'
import glob, hashlib, json, os, sys
d, extra = sys.argv[1], [e.split(':') for e in sys.argv[2:]]
sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
roh = {e[1] for e in extra if e[0] == 'roh'}
f = [{'id': os.path.basename(p)[:-4], 'name': 'Datei.pdf', 'groesse': os.path.getsize(p), 'sha256': sha(p)}
     for p in sorted(glob.glob(d + '/dateien/*/*/*.bin')) if not os.path.islink(p) and os.path.basename(p)[:-4] not in roh]
for art, i, *rest in extra:
    p = glob.glob(f'{d}/dateien/*/*/{i}.bin')
    if art == 'fehlt':
        f.append({'id': i, 'name': 'fehlt.pdf', 'groesse': 3, 'sha256': '0' * 64})
    elif art == 'roh':
        f.append({'name': 'Vorlage.docx', 'roh': i, 'sha256Roh': sha(p[0]) if p else '0' * 64})
    else:
        next(x for x in f if x.get('id') == i)['groesse'] = int(rest[0])
open(d + '/qs-dokumente.php', 'w').write('<?php http_response_code(404); exit; ?>\n' + json.dumps({'liste': [{'id': 'd1', 'dateien': f}]}))
PY
ablage() { mkdir -p "$W/daten/dateien/qs/$(echo "$1" | cut -c1-2)"; printf '%s' "$2" > "$W/daten/dateien/qs/$(echo "$1" | cut -c1-2)/$1.bin"; }
verweise() { python3 "$T/verweise.py" "$W/daten" "$@"; }
lauf() { sleep 1; sh "$W/deploy/sichern.sh" --jetzt > "$W/aus.txt" 2>&1; }   # eigene Zeit je Lauf
stand() { ls -1d "$W"/sicherungen/dateien/2* | sed -n "${1}p"; }   # n-ter Stand, ältester zuerst
neuester() { ls -1d "$W"/sicherungen/dateien/2* | tail -1; }
inhalt() { (cd "$W/sicherungen" && find . \( -name .sperre -o -name .letzter-fehler \) -prune -o -print | sort); }
ablage aa00000000000000000001 'Inhalt eins'; ablage ab00000000000000000002 'Inhalt zwei'; ablage ac00000000000000000003 'Inhalt drei'
mkdir -p "$W/daten/dateien/.teile"; echo halb > "$W/daten/dateien/.teile/x.tmp"; ln -s /etc/hostname "$W/daten/dateien/qs/aa/ad00000000000000000004.bin"
verweise; lauf
S1=$(stand 1); export S1
ok "Dateiablage: erster Stand mit allen Dateien, ohne halbe Uploads und Verweise, Archiv ohne dateien/, gleiche Zeit wie das Archiv" '[ "$(feld "$W/daten" ok)" = True ] \
  && [ "$(find "$S1" -type f | wc -l)" = 3 ] && cmp -s "$S1/qs/ab/ab00000000000000000002.bin" "$W/daten/dateien/qs/ab/ab00000000000000000002.bin" && [ ! -e "$S1/.teile" ] \
  && [ -z "$(find "$S1" -type l)" ] && ! tar tzf "$W"/sicherungen/daten-*.tar.gz | grep -q "dateien/" && [ -f "$W/sicherungen/daten-${S1##*/}.tar.gz" ]'
ok "Dateiablage: Status nennt Anzahl, Größe, neu kopiert, Stände, belegt und fehlend; nichts Vorläufiges bleibt liegen" '[ "$(feld "$W/daten" ablage.anzahl)" = 3 ] \
  && [ "$(feld "$W/daten" ablage.groesse)" = 33 ] && [ "$(feld "$W/daten" ablage.neu)" = 33 ] && [ "$(feld "$W/daten" ablage.staende)" = 1 ] \
  && [ "$(feld "$W/daten" ablage.belegt)" = 33 ] && [ "$(feld "$W/daten" ablage.fehlend)" = 0 ] && [ "$(feld "$W/daten" ablage.zustand)" = ok ] && [ "$(feld "$W/daten" meldung)" = "" ] && [ "$(stat -c %a "$S1")" = 700 ] \
  && [ -z "$(find "$W/sicherungen" -name "*.tmp" -o -name ".dateisicherung-fehler")" ]'
rm -r "$W/daten/dateien/qs/ac"; ablage ae00000000000000000005 'neue Datei'; verweise; lauf
S2=$(stand 2); export S2
ok "Dateiablage: zweiter Stand verweist auf unveränderte Dateien, kopiert nur die neue, gelöschte bleibt im ersten" '[ "$(feld "$W/daten" ok)" = True ] \
  && [ "$(stat -c %i "$S1/qs/aa/aa00000000000000000001.bin")" = "$(stat -c %i "$S2/qs/aa/aa00000000000000000001.bin")" ] \
  && [ -f "$S2/qs/ae/ae00000000000000000005.bin" ] && [ ! -e "$S2/qs/ac/ac00000000000000000003.bin" ] && [ -f "$S1/qs/ac/ac00000000000000000003.bin" ] \
  && [ "$(feld "$W/daten" ablage.neu)" = 10 ] && [ "$(feld "$W/daten" ablage.anzahl)" = 3 ] && [ "$(feld "$W/daten" ablage.staende)" = 2 ] && [ "$(feld "$W/daten" ablage.belegt)" = 43 ]'
# Upload während des Archivs (erst die Datei, dann das Dokument): die tar-Attrappe legt beides kurz vor dem Packen an
mkdir "$W/bin-tar"; ECHT_TAR=$(command -v tar); export ECHT_TAR
cat > "$W/bin-tar/tar" <<'EOF2'
#!/bin/sh
if [ "$1" = czf ] && [ ! -e "$W/tar-einmal" ]; then
  touch "$W/tar-einmal"; mkdir -p "$W/daten/dateien/qs/aj"; printf 'waehrend' > "$W/daten/dateien/qs/aj/aj00000000000000000010.bin"; python3 "$T/verweise.py" "$W/daten"
fi
exec "$ECHT_TAR" "$@"
EOF2
chmod +x "$W/bin-tar/tar"; sleep 1
PATH="$W/bin-tar:$PATH" sh "$W/deploy/sichern.sh" --jetzt > "$W/aus.txt" 2>&1
ok "Datei kommt während des Archivs hinzu: im Stand desselben Laufs, keine Warnung" '[ "$(feld "$W/daten" ok)" = True ] && [ -e "$W/tar-einmal" ] && [ "$(feld "$W/daten" ablage.fehlend)" = 0 ] \
  && cmp -s "$(neuester)/qs/aj/aj00000000000000000010.bin" "$W/daten/dateien/qs/aj/aj00000000000000000010.bin" && [ "$(feld "$W/daten" meldung)" = "" ]'
# gleiches Pfadmuster wie PHP: Datei über ablage_ablegen() (lib/dateiablage.php) erzeugen
if command -v php >/dev/null 2>&1; then
  PHP_ID=$(php -r 'define("WA_API", true); $GLOBALS["DATA"] = $argv[1]; require $argv[2] . "/app/api/storage.php"; require $argv[2] . "/app/api/lib/dateiablage.php";
    echo ablage_ablegen("qs", "%PDF-1.4 Probe")["id"];' "$W/daten" "$REPO"); export PHP_ID
  verweise; lauf
  ok "Datei aus ablage_ablegen() (PHP) liegt im Stand" '[ "$(feld "$W/daten" ok)" = True ] && [ "$(feld "$W/daten" ablage.fehlend)" = 0 ] \
    && cmp -s "$(neuester)/qs/$(echo "$PHP_ID" | cut -c1-2)/$PHP_ID.bin" "$W/daten/dateien/qs/$(echo "$PHP_ID" | cut -c1-2)/$PHP_ID.bin"'
else
  echo "HINWEIS: kein PHP – Prüfung des Pfadmusters übersprungen"
fi
ablage ag00000000000000000007 'Rohfassung'; verweise fehlt:af00000000000000000006 roh:ag00000000000000000007 roh:ah00000000000000000008
R=0; lauf || R=$?; export R
ok "Verweise auf Dateien, die in Ablage und Sicherung fehlen (auch Rohfassung): nur Warnung, Archiv und Stand festgeschrieben, Zustand kritisch (über 1 %)" '[ "$R" = 0 ] && [ "$(feld "$W/daten" ok)" = True ] \
  && [ "$(feld "$W/daten" ablage.fehlend)" = 2 ] && [ "$(feld "$W/daten" ablage.zustand)" = kritisch ] && [ -f "$(neuester)/qs/ag/ag00000000000000000007.bin" ] && [ -f "$W/sicherungen/daten-$(basename "$(neuester)").tar.gz" ] \
  && [ "$(feld "$W/daten" meldung)" = "2 Datei(en) fehlen in Ablage und Sicherung (af00000000000000000006, ah00000000000000000008), Liste: sicherungen/.dateien-fehlend" ] \
  && [ "$(cat "$W/sicherungen/.dateien-fehlend")" = "$(printf "af00000000000000000006\tqs-dokumente\tfehlt in Ablage und Sicherung\nah00000000000000000008\tqs-dokumente\tfehlt in Ablage und Sicherung")" ]'
ok "Lese-Befehl fehlende: Kennung, Dokument und Befund für den Betreiber" '[ "$(python3 "$W/deploy/dateien_sichern.py" fehlende "$W/daten/dateien" "$W/daten")" \
  = "$(printf "af00000000000000000006\tqs-dokumente\tfehlt\nah00000000000000000008\tqs-dokumente\tfehlt")" ]'
verweise
python3 -c "import os, sys; p = sys.argv[1]; t = os.stat(p); open(p, 'r+b').write(b'X'); os.utime(p, ns=(t.st_atime_ns, t.st_mtime_ns))" "$(neuester)/qs/ab/ab00000000000000000002.bin"
ALT=$(neuester); export ALT
R=0; lauf || R=$?; export R
ok "beschädigte Kopie in der Sicherung, Datei in der Ablage richtig: im neuen Stand frisch kopiert, Warnung" '[ "$R" = 0 ] && [ "$(feld "$W/daten" ok)" = True ] && [ "$(feld "$W/daten" ablage.zustand)" = warnung ] \
  && [ "$(feld "$W/daten" meldung)" = "1 beschädigte Kopie(n) in der Sicherung neu kopiert (ab00000000000000000002)" ] \
  && cmp -s "$(neuester)/qs/ab/ab00000000000000000002.bin" "$W/daten/dateien/qs/ab/ab00000000000000000002.bin" \
  && [ "$(stat -c %i "$(neuester)/qs/ab/ab00000000000000000002.bin")" != "$(stat -c %i "$ALT/qs/ab/ab00000000000000000002.bin")" ] && [ ! -e "$W/sicherungen/.dateien-fehlend" ]'
# Datei verschwindet während des Kopierens (Entwurf gelöscht): übersprungen und eingeteilt statt Abbruch
ablage ai00000000000000000009 'gleich weg'; verweise
python3 - "$W/deploy" "$W/daten/dateien" "$W/sicherungen/dateien" "$W/daten" > "$W/kopieren.txt" 2>&1 <<'PY' && R=0 || R=$?; export R
import os, shutil, sys
sys.path.insert(0, sys.argv[1])
import dateien_sichern
kopie = shutil.copy2
def weg(quelle, ziel, **k):
    os.unlink(quelle)
    return kopie(quelle, ziel, **k)
shutil.copy2 = weg
sys.argv = ['dateien_sichern.py', 'pruefen', sys.argv[2], sys.argv[3], '2099-01-01_000000', sys.argv[4]]
dateien_sichern.main()
PY
ok "Datei verschwindet beim Kopieren: kein Fehler, nicht im Stand, als fehlend gemeldet" '[ "$R" = 0 ] && grep -q "^1 Datei(en) fehlen in Ablage und Sicherung (ai00000000000000000009)" "$W/kopieren.txt" \
  && [ ! -e "$W/sicherungen/dateien/2099-01-01_000000.tmp/qs/ai/ai00000000000000000009.bin" ] && [ ! -e "$W/daten/dateien/qs/ai/ai00000000000000000009.bin" ]'
rm -rf "$W/sicherungen/dateien/2099-01-01_000000.tmp"; rmdir "$W/daten/dateien/qs/ai"
# Größe passt nicht zum Dokument: kein Abbruch. Gesichert wird die passende Fassung des vorigen Stands, sonst die der Ablage.
verweise; VORIG=$(neuester); export VORIG
printf 'Inhalt zwei, später geändert' > "$W/daten/dateien/qs/ab/ab00000000000000000002.bin"   # das Dokument nennt weiter die alte Größe
R=0; lauf || R=$?; export R
ok "Datei in der Ablage mit anderer Größe als im Dokument, passende Fassung im vorigen Stand: diese gesichert (fester Verweis), Warnung statt Abbruch" '[ "$R" = 0 ] \
  && [ "$(feld "$W/daten" ok)" = True ] && [ "$(feld "$W/daten" ablage.zustand)" = warnung ] && [ "$(cat "$(neuester)/qs/ab/ab00000000000000000002.bin")" = "Inhalt zwei" ] \
  && [ "$(stat -c %i "$(neuester)/qs/ab/ab00000000000000000002.bin")" = "$(stat -c %i "$VORIG/qs/ab/ab00000000000000000002.bin")" ] \
  && [ "$(feld "$W/daten" meldung)" = "1 Datei(en) in der Ablage mit anderer Größe als im Dokument, passende Fassung aus Stand ${VORIG##*/} gesichert (ab00000000000000000002)" ]'
verweise groesse:ab00000000000000000002:999
R=0; lauf || R=$?; export R
ok "Größe passt in keiner Fassung: die der Ablage gesichert, Warnung statt Abbruch" '[ "$R" = 0 ] && [ "$(feld "$W/daten" ok)" = True ] \
  && cmp -s "$(neuester)/qs/ab/ab00000000000000000002.bin" "$W/daten/dateien/qs/ab/ab00000000000000000002.bin" \
  && [ "$(feld "$W/daten" meldung)" = "1 Datei(en) mit anderer Größe als im Dokument, vorhandene Fassung gesichert (ab00000000000000000002)" ]'
ablage ab00000000000000000002 'Inhalt zwei'; verweise
# Störung der Sicherung selbst (Datendatei im Archiv fehlerhaft): nichts dieses Laufs bleibt. 30 Fehlversuche hintereinander
# (das Release versucht es alle 2 Minuten) lassen ältere Sicherungen unangetastet.
vor() { date -u -d "$1" +%Y-%m-%d_%H%M%S; }
alt() { for Z in "$@"; do touch "$W/sicherungen/daten-$Z.tar.gz" "$W/sicherungen/anmeldung-$Z.dump"; mkdir "$W/sicherungen/dateien/$Z"; done; }   # Attrappen früherer Läufe
TAG10=$(date -u -d '10 days ago' +%Y-%m-%d); Z40=$(vor '40 days ago'); export TAG10 Z40
alt "$Z40" "${TAG10}_080000" "${TAG10}_120000" "${TAG10}_180000"
echo '{kaputt' > "$W/daten/defekt.php"
inhalt > "$W/vorher.txt"
R=0; lauf || R=$?; export R
ok "Störung der Sicherung (Datendatei im Archiv fehlerhaft): Fehler, kein Archiv, kein Stand, kein .tmp" '[ "$R" = 1 ] && [ "$(feld "$W/daten" ok)" = False ] \
  && [ "$(feld "$W/daten" fehler)" = 1 ] && [ "$(inhalt)" = "$(cat "$W/vorher.txt")" ]'
N=0; while [ "$N" -lt 30 ]; do sh "$W/deploy/sichern.sh" --jetzt >/dev/null 2>&1 || true; N=$((N + 1)); done
ok "30 Fehlversuche hintereinander: kein älteres Archiv, keine Keycloak-Sicherung und kein Stand gelöscht" '[ "$(inhalt)" = "$(cat "$W/vorher.txt")" ]'
rm "$W/daten/defekt.php"; lauf
ok "Aufbewahrung: weniger als 30 Läufe – alle bleiben, auch ältere als 30 Tage (Schutz bei verstellter Uhr)" '[ "$(feld "$W/daten" ok)" = True ] \
  && [ -f "$W/sicherungen/daten-$Z40.tar.gz" ] && [ -d "$W/sicherungen/dateien/${TAG10}_080000" ]'
VOR=$(ls "$W"/sicherungen/daten-*.tar.gz | wc -l); export VOR
N=1; while [ "$N" -le 31 ]; do alt "$(vor "-$((N % 2 + 1)) days -$N minutes")"; N=$((N + 1)); done   # je Tag unter dem Deckel von 24
lauf
ok "Aufbewahrung nach Zeit: alle Läufe der letzten 7 Tage, der letzte jedes Tages bis 30 Tage; Archiv, Keycloak-Sicherung und Stand gemeinsam" '[ "$(feld "$W/daten" ok)" = True ] \
  && [ ! -e "$W/sicherungen/daten-$Z40.tar.gz" ] && [ ! -e "$W/sicherungen/anmeldung-$Z40.dump" ] && [ ! -e "$W/sicherungen/dateien/$Z40" ] \
  && [ ! -e "$W/sicherungen/daten-${TAG10}_080000.tar.gz" ] && [ ! -e "$W/sicherungen/dateien/${TAG10}_120000" ] && [ ! -e "$W/sicherungen/anmeldung-${TAG10}_120000.dump" ] \
  && [ -f "$W/sicherungen/daten-${TAG10}_180000.tar.gz" ] && [ -f "$W/sicherungen/anmeldung-${TAG10}_180000.dump" ] && [ -d "$W/sicherungen/dateien/${TAG10}_180000" ] \
  && [ "$(ls "$W"/sicherungen/daten-*.tar.gz | wc -l)" = $((VOR + 31 + 1 - 3)) ] && [ "$(ls "$W"/sicherungen/dateien | wc -l)" = $((VOR + 31 + 1 - 3)) ] \
  && [ "$(feld "$W/daten" anzahl)" = $((VOR + 31 + 1 - 3)) ]'
TAG3=$(date -u -d '3 days ago' +%Y-%m-%d); export TAG3
N=10; while [ "$N" -lt 50 ]; do alt "${TAG3}_10${N}00"; N=$((N + 1)); done   # 40 Läufe an einem Tag (Release wiederholt nach Keycloak-Fehler)
lauf
ok "Aufbewahrung: je Tag der letzten 7 höchstens die 24 neuesten Läufe (Archiv, Keycloak-Sicherung und Stand)" '[ "$(feld "$W/daten" ok)" = True ] \
  && [ "$(ls "$W"/sicherungen/daten-"$TAG3"_* | wc -l)" = 24 ] && [ "$(ls "$W"/sicherungen/anmeldung-"$TAG3"_* | wc -l)" = 24 ] && [ "$(ls -d "$W"/sicherungen/dateien/"$TAG3"_* | wc -l)" = 24 ] \
  && [ -f "$W/sicherungen/daten-${TAG3}_102600.tar.gz" ] && [ ! -e "$W/sicherungen/daten-${TAG3}_102500.tar.gz" ]'
# Sperre: läuft schon eine Sicherung, wartet ein zweiter Aufruf mit --jetzt (Timer, Release) und lässt deren .tmp in Ruhe
mkdir "$W/sicherungen/dateien/2099-01-02_000000.tmp"
( flock 9; touch "$W/gesperrt"; while [ ! -e "$W/frei" ]; do sleep 0.1; done ) 9>"$W/sicherungen/.sperre" & SPERRE=$!
while [ ! -e "$W/gesperrt" ]; do sleep 0.1; done
T0=$(feld "$W/daten" t); export T0
lauf & LAUF=$!
sleep 2
ok "Sperre: zweiter Lauf mit --jetzt wartet und ändert solange weder Status noch fremdes .tmp" 'kill -0 "$LAUF" && [ "$(feld "$W/daten" t)" = "$T0" ] \
  && [ -d "$W/sicherungen/dateien/2099-01-02_000000.tmp" ]'
touch "$W/frei"; wait "$SPERRE"; R=0; wait "$LAUF" || R=$?; export R
ok "… und sichert, sobald die Sperre frei ist; Rest des abgebrochenen Laufs aufgeräumt" '[ "$R" = 0 ] && [ "$(feld "$W/daten" ok)" = True ] && [ "$(feld "$W/daten" t)" != "$T0" ] \
  && [ -z "$(find "$W/sicherungen" -name "*.tmp")" ]'
( flock 9; touch "$W/gesperrt2"; while [ ! -e "$W/frei2" ]; do sleep 0.1; done ) 9>"$W/sicherungen/.sperre" & SPERRE=$!
while [ ! -e "$W/gesperrt2" ]; do sleep 0.1; done
touch -d '2 days ago' "$W"/sicherungen/daten-*.tar.gz; rm -f "$W/sicherungen/.letzter-fehler"   # sonst endet der Aufruf ohne --jetzt vor der Sperre
T0=$(feld "$W/daten" t); export T0
R=0; sh "$W/deploy/sichern.sh" > "$W/aus.txt" 2> "$W/fehler.txt" || R=$?; export R
touch "$W/frei2"; wait "$SPERRE"
ok "Sperre ohne --jetzt (aktualisieren.sh): endet sofort mit Fehler, Grund auf stderr (das Release verwirft stdout)" '[ "$R" = 1 ] && grep -q "läuft bereits" "$W/fehler.txt" \
  && ! grep -q "läuft bereits" "$W/aus.txt" && [ "$(feld "$W/daten" t)" = "$T0" ]'
STAND=$(neuester); STAND=${STAND##*/}
mkdir "$W/zurueck"; tar xzf "$W/sicherungen/daten-$STAND.tar.gz" -C "$W/zurueck"; cp -a "$W/sicherungen/dateien/$STAND" "$W/zurueck/dateien"
ok "Wiederherstellung: Archiv und Stand derselben Zeit ergeben Daten und Dateiablage (ohne halbe Uploads)" 'diff -r -x .teile -x ad00000000000000000004.bin "$W/daten/dateien" "$W/zurueck/dateien" >/dev/null \
  && cmp -s "$W/daten/qs-dokumente.php" "$W/zurueck/qs-dokumente.php" && [ "$(stat -c %h "$W/zurueck/dateien/qs/aa/aa00000000000000000001.bin")" = 1 ]'
mkdir "$W/bin-df"; printf '#!/bin/sh\necho "Filesystem 1024-blocks Used Available Capacity Mounted"\necho "/dev/x 400000000 399000000 1048576 99%% /"\n' > "$W/bin-df/df"; chmod +x "$W/bin-df/df"
ablage ak00000000000000000011 'noch eine'; verweise; sleep 1
ANZ_VOR=$(ls "$W"/sicherungen/daten-*.tar.gz | wc -l); export ANZ_VOR
PATH="$W/bin-df:$PATH" sh "$W/deploy/sichern.sh" --jetzt >/dev/null 2>&1 || true
ok "zu wenig Platz (1 GB frei): Abbruch vor dem Sichern mit Meldung im Status" '[ "$(feld "$W/daten" ok)" = False ] && grep -q "zu wenig Speicherplatz: 1,0 GB frei, nötig 5,0 GB" "$W/daten/sicherung.php" \
  && [ "$(ls "$W"/sicherungen/daten-*.tar.gz | wc -l)" = "$ANZ_VOR" ]'
rm "$W/deploy/dateien_sichern.py"; lauf
LATEST=$(ls -1 "$W"/sicherungen/daten-*.tar.gz | tail -1); export LATEST
ok "ohne Werkzeug (Sicherung vor dem Release mit altem deploy/): Dateiablage wie bisher im Archiv" '[ "$(feld "$W/daten" ok)" = True ] && tar tzf "$LATEST" | grep -q "dateien/qs/ak/ak00000000000000000011.bin" \
  && ! tar tzf "$LATEST" | grep -q "x.tmp" && [ "$(feld "$W/daten" ablage)" = None ]'
chmod -R u+rwx "$W" 2>/dev/null; rm -rf "$W"
# Test-Uhr: VERSATZ verstellt sie („+1 day“; relative Angaben wie „7 days ago“ gelten von dort aus), FEST liefert diese
# Zeitmarke statt der aktuellen (mit FEST_EINMAL nur beim ersten Aufruf)
mkdir "$T/bin-uhr"; ECHT_DATE=$(command -v date); export ECHT_DATE
cat > "$T/bin-uhr/date" <<'EOF2'
#!/bin/sh
if [ -n "${FEST:-}" ] && [ "$*" = "-u +%Y-%m-%d_%H%M%S" ] && [ ! -e "${FEST_EINMAL:-/-}" ]; then [ -z "${FEST_EINMAL:-}" ] || touch "$FEST_EINMAL"; echo "$FEST"; exit 0; fi
for a; do case $a in *ago) exec "$ECHT_DATE" -u -d "$("$ECHT_DATE" -u -d "${VERSATZ:-now}" '+%Y-%m-%d %H:%M:%S') $a" +%Y-%m-%d_%H%M%S ;; esac; done
exec "$ECHT_DATE" -d "${VERSATZ:-now}" "$@"
EOF2
chmod +x "$T/bin-uhr/date"
uhr() { PATH="$T/bin-uhr:$PATH" sh "$W/deploy/sichern.sh" --jetzt > "$W/aus.txt" 2>&1; }

# ── Nie eine verwiesene Datei verlieren: fehlt sie in der Ablage, trägt jeder Stand sie aus dem vorigen weiter ──
umgebung "$T/v"
ablage aa00000000000000000001 'Inhalt eins'; ablage ab00000000000000000002 'Inhalt zwei'; ablage ac00000000000000000003 'Inhalt drei'; verweise; lauf
S0=$(neuester); cp -a "$W/daten/dateien" "$W/original"; export S0
rm -rf "$W/daten/dateien"   # Ablage verloren, die Dokumente verweisen weiter auf die Dateien
R=0; lauf || R=$?; export R
S1=$(neuester); export S1
ok "Ablage verloren: alle verwiesenen Dateien aus dem vorigen Stand übernommen (feste Verweise), Sicherung erfolgreich, Zustand kritisch" '[ "$R" = 0 ] \
  && [ "$(feld "$W/daten" ok)" = True ] && [ "$(feld "$W/daten" ablage.zustand)" = kritisch ] && [ "$(feld "$W/daten" ablage.anzahl)" = 3 ] && [ "$(feld "$W/daten" ablage.fehlend)" = 3 ] \
  && [ "$(stat -c %i "$S1/qs/ab/ab00000000000000000002.bin")" = "$(stat -c %i "$S0/qs/ab/ab00000000000000000002.bin")" ] \
  && [ "$(feld "$W/daten" meldung)" = "3 Datei(en) fehlen in der Ablage, in der Sicherung erhalten (Stand ${S1##*/}), zurückholen: python3 deploy/dateien_sichern.py zurueckholen sicherungen/dateien" ]'
ok "Liste .dateien-fehlend: je Datei Kennung, Dokument und Ziel in der Ablage, kein Befehl" '[ "$(wc -l < "$W/sicherungen/.dateien-fehlend")" = 3 ] \
  && [ "$(sed -n 2p "$W/sicherungen/.dateien-fehlend")" = "$(printf "ab00000000000000000002\tqs-dokumente\t%s" "$W/daten/dateien/qs/ab/ab00000000000000000002.bin")" ]'
N=1; while [ "$N" -le 31 ]; do export VERSATZ="+$N days"; uhr || echo "Lauf +$N Tage: $(tail -1 "$W/aus.txt")"; N=$((N + 1)); done   # 31 Tage täglich gesichert
ok "nach 31 Tagen und 31 Läufen: frühere Stände aufgeräumt, die Dateien liegen weiter unverändert im neuesten Stand" '[ ! -e "$S0" ] && [ ! -e "$S1" ] \
  && [ "$(feld "$W/daten" ok)" = True ] && [ "$(feld "$W/daten" ablage.zustand)" = kritisch ] && diff -r "$W/original" "$(neuester)" >/dev/null'
# Ausweg wie in docs/entwickler/08-betrieb.md: „zurueckholen“ (als root) schreibt als Webserver (uid 33) und folgt keinem
# Verweis, den der Container in der Ablage anlegt: hier ein Verweis am Ziel und einer als Ordner auf Dateien des Hosts
mkdir -p "$W/daten/dateien/qs/aa"; [ "$(id -u)" != 0 ] || { chmod 755 "$T"; chown -R 33:33 "$W/daten"; }   # wie im Betrieb: Datenordner des Webservers
echo ORIGINAL > "$T/host-datei"; chmod 644 "$T/host-datei"; mkdir "$T/host-ordner"; HOST_VOR=$(stat -c %U:%G:%a "$T/host-datei" "$T/host-ordner"); export HOST_VOR
ln -s "$T/host-datei" "$W/daten/dateien/qs/aa/aa00000000000000000001.bin"; ln -s "$T/host-ordner" "$W/daten/dateien/qs/ab"
R=0; python3 "$W/deploy/dateien_sichern.py" zurueckholen "$W/sicherungen/dateien" > "$W/zurueck.txt" 2>&1 || R=$?; export R
ok "zurueckholen: Verweis am Ziel ersetzt statt verfolgt, Verweis als Ordner abgelehnt, Dateien des Hosts unverändert" '[ "$R" = 1 ] \
  && [ "$(cat "$T/host-datei")" = ORIGINAL ] && [ "$(stat -c %U:%G:%a "$T/host-datei" "$T/host-ordner")" = "$HOST_VOR" ] && [ -z "$(ls -A "$T/host-ordner")" ] \
  && [ ! -L "$W/daten/dateien/qs/aa/aa00000000000000000001.bin" ] && cmp -s "$W/original/qs/aa/aa00000000000000000001.bin" "$W/daten/dateien/qs/aa/aa00000000000000000001.bin" \
  && grep -q "^ab00000000000000000002: " "$W/zurueck.txt" && grep -q "^2 Datei(en) zurückgeholt, 1 nicht" "$W/zurueck.txt"'
rm "$W/daten/dateien/qs/ab"; python3 "$W/deploy/dateien_sichern.py" zurueckholen "$W/sicherungen/dateien" >/dev/null || true   # Ergebnis prüft der nächste Test
export VERSATZ="+32 days"; uhr; unset VERSATZ
ok "Ausweg: zurueckholen holt jede Datei als eigene Datei des Webservers zurück (kein fester Verweis in die Sicherung), danach ohne Warnung" 'diff -r "$W/original" "$W/daten/dateien" >/dev/null \
  && [ "$(stat -c %h "$W/daten/dateien/qs/aa/aa00000000000000000001.bin")" = 1 ] && { [ "$(id -u)" != 0 ] || [ "$(stat -c %u:%g "$W/daten/dateien/qs/aa/aa00000000000000000001.bin")" = 33:33 ]; } \
  && [ "$(feld "$W/daten" ok)" = True ] && [ "$(feld "$W/daten" meldung)" = "" ] && [ "$(feld "$W/daten" ablage.zustand)" = ok ] && [ ! -e "$W/sicherungen/.dateien-fehlend" ]'
chmod -R u+rwx "$W" 2>/dev/null; rm -rf "$W"

# ── Uhr, Zeitmarke, Prüfsummen-Runde, Dokumente, hängender Keycloak-Abzug ──
umgebung "$T/x"
ablage aa00000000000000000001 'Inhalt eins'; ablage ab00000000000000000002 'Inhalt zwei'; verweise; lauf
S0=$(neuester); export S0
N=1; while [ "$N" -le 20 ]; do Z=$(date -u -d "$N days ago" +%Y-%m-%d); touch "$W/sicherungen/daten-${Z}_023000.tar.gz"; mkdir "$W/sicherungen/dateien/${Z}_023000"; N=$((N + 1)); done
VOR=$(ls "$W"/sicherungen/daten-*.tar.gz | wc -l); export VOR
export VERSATZ="+365 days"; R=0; uhr || R=$?; unset VERSATZ; export R
ZUKUNFT=$(neuester); export ZUKUNFT
ok "Uhr ein Jahr vorgestellt: gesichert, nichts aufgeräumt, Warnung Uhrzeit prüfen" '[ "$R" = 0 ] && [ "$(feld "$W/daten" ok)" = True ] \
  && [ "$(ls "$W"/sicherungen/daten-*.tar.gz | wc -l)" = $((VOR + 1)) ] && [ "$(ls -d "$W"/sicherungen/dateien/2* | wc -l)" = $((VOR + 1)) ] \
  && [ "$(feld "$W/daten" meldung)" = "Uhrzeit prüfen: letzter Lauf ${S0##*/} liegt über 2 Tage zurück, ältere Sicherungen nicht aufgeräumt" ]'
ablage ac00000000000000000003 'nach der Uhr'; verweise; lauf; lauf
heute() { for S in "$W"/sicherungen/dateien/2*; do [ "$S" = "$ZUKUNFT" ] || echo "$S"; done; }   # Stände ohne den mit Zukunftszeit
S2=$(heute | tail -1); S1=$(heute | tail -2 | head -1); export S1 S2
ok "Uhr wieder richtig: der Stand mit Zukunftszeit dient nicht als Vorlage, neue Dateien werden einmal kopiert und dann verlinkt" '[ "$(feld "$W/daten" ok)" = True ] \
  && [ "$(stat -c %i "$S2/qs/ac/ac00000000000000000003.bin")" = "$(stat -c %i "$S1/qs/ac/ac00000000000000000003.bin")" ] && [ "$(feld "$W/daten" ablage.neu)" = 0 ] \
  && [ -d "$ZUKUNFT" ] && [ "$(feld "$W/daten" meldung)" = "" ]'
inhalt > "$W/vorher.txt"; cp "$W/sicherungen/daten-${S2##*/}.tar.gz" "$W/archiv-vorher"
export FEST="${S2##*/}"; R=0; uhr || R=$?; export R
ok "Zeitmarke schon vergeben (Uhr zurückgestellt): Abbruch mit Meldung, nichts überschrieben" '[ "$R" = 1 ] && [ "$(feld "$W/daten" ok)" = False ] \
  && feld "$W/daten" meldung | grep -q "^Zeitmarke ${S2##*/} schon vergeben" && [ "$(inhalt)" = "$(cat "$W/vorher.txt")" ] && cmp -s "$W/archiv-vorher" "$W/sicherungen/daten-${S2##*/}.tar.gz"'
export FEST_EINMAL="$W/fest-einmal"; R=0; uhr || R=$?; unset FEST FEST_EINMAL; export R
ok "Zeitmarke in derselben Sekunde vergeben: eine Sekunde später gesichert, der vorige Lauf bleibt unverändert" '[ "$R" = 0 ] && [ -e "$W/fest-einmal" ] && [ "$(feld "$W/daten" ok)" = True ] \
  && cmp -s "$W/archiv-vorher" "$W/sicherungen/daten-${S2##*/}.tar.gz" && [ "$(ls "$W"/sicherungen/daten-*.tar.gz | wc -l)" = $(($(grep -c "^./daten-" "$W/vorher.txt") + 1)) ]'
# rotierende Prüfsummen-Stichprobe: ohne Zufall prüft sie jede Datei einmal in 30 aufeinanderfolgenden Tagen
python3 -c "import os, sys; p = sys.argv[1]; t = os.stat(p); open(p, 'r+b').write(b'X'); os.utime(p, ns=(t.st_atime_ns, t.st_mtime_ns))" "$(heute | tail -1)/qs/ab/ab00000000000000000002.bin"
python3 - "$W/deploy" "$W/daten/dateien" "$W/sicherungen/dateien" "$W/daten" > "$W/runde.txt" 2>&1 <<'PY' && R=0 || R=$?; export R
import shutil, sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import dateien_sichern as d
d.STICHPROBE = 0
for n in range(30):
    zeit = f'{date.today() + timedelta(1 + n)}_000000'   # zwischen dem heutigen Stand und dem mit Zukunftszeit
    print(zeit, *d.pruefen(Path(sys.argv[2]), Path(sys.argv[3]), zeit, [Path(sys.argv[4])])[1])
    shutil.rmtree(Path(sys.argv[3]) / f'{zeit}.tmp')
PY
ok "rotierende Stichprobe: beschädigte Kopie an genau einem von 30 Tagen erkannt und geheilt" '[ "$R" = 0 ] && [ "$(grep -c "1 beschädigte Kopie(n) in der Sicherung neu kopiert (ab00000000000000000002)" "$W/runde.txt")" = 1 ]'
# hängender Keycloak-Abzug: die Frist (hier 2 s statt KC_FRIST) beendet ihn, die Sperre ist danach frei
mkdir -p "$W/deploy/anmeldung" "$W/daten-anmeldung" "$W/bin-frist"; touch "$W/deploy/anmeldung/docker-compose.anmeldung.yml"
printf '#!/bin/sh\ncase "$1" in ps) echo 0123abcd ;; exec) sleep 60 ;; esac\n' > "$W/kc-haengt.sh"
ECHT_TIMEOUT=$(command -v timeout); export ECHT_TIMEOUT
printf '#!/bin/sh\n[ "$1 $2" = "-k 10" ] || exit 99   # nach der Frist hart beenden, falls der Container TERM nicht beachtet\nshift 3; exec "$ECHT_TIMEOUT" 2 "$@"\n' > "$W/bin-frist/timeout"; chmod +x "$W/bin-frist/timeout"
A0=$(date +%s); R=0; WA_KC_COMPOSE="sh $W/kc-haengt.sh" PATH="$W/bin-frist:$PATH" sh "$W/deploy/sichern.sh" --jetzt > "$W/aus.txt" 2>&1 || R=$?; DAUER=$(($(date +%s) - A0)); export R DAUER
ok "Keycloak-Abzug hängt: nach der Frist Fehler mit Grund, Geschäftsdaten gesichert, kein Warten auf den Container" '[ "$R" = 1 ] && [ "$DAUER" -lt 30 ] \
  && [ "$(feld "$W/daten" anmeldung)" = fehler ] && feld "$W/daten" meldung | grep -q "Keycloak) fehlgeschlagen: keine Antwort nach 300 s"'
rm -rf "$W/deploy/anmeldung" "$W/daten-anmeldung"
A0=$(date +%s); lauf; DAUER=$(($(date +%s) - A0)); export DAUER
ok "… danach ist die Sperre frei: der nächste Lauf sichert sofort" '[ "$(feld "$W/daten" ok)" = True ] && [ "$DAUER" -lt 30 ]'
# Dokumente im Dateispeicher je Datei gelesen, so nachsichtig wie die Archivprüfung; Unlesbares nur als Warnung mit Namen
G='<?php http_response_code(404); exit; ?>'
printf '{"dateien":[{"id":"af00000000000000000006","groesse":3,"sha256":"%s"}]}' "$(printf '0%.0s' $(seq 64))" > "$W/daten/notiz.php"   # ohne Sperrzeile
printf '%s\n{"a":1}' "$G" > "$W/daten/angebot.alt.php"; printf '%s\n"text"' "$G" > "$W/daten/zaehler.php"; ln -s qs-dokumente.php "$W/daten/kopie.php"
R=0; lauf || R=$?; export R
ok "Dokumente ohne Sperrzeile, mit Punkt im Namen oder skalarem JSON: gesichert und gelesen; ein Verweis als Dokument nur Warnung mit Namen" '[ "$R" = 0 ] \
  && [ "$(feld "$W/daten" ok)" = True ] && feld "$W/daten" meldung | grep -q "1 Datei(en) fehlen in Ablage und Sicherung (af00000000000000000006)" \
  && feld "$W/daten" meldung | grep -q "1 Dokument(e) nicht lesbar, Verweise darin nicht geprüft (kopie.php)"'
# Dokumentname mit Tabulator und Shell-Befehl (der Container kann ihn anlegen): nur Warnung, nie in Liste oder Ausweg
printf '%s\n{"a":{"id":"zz0000000000000000000z","groesse":1,"sha256":"%s"}}' "$G" "$(printf '0%.0s' $(seq 64))" > "$W/daten/$(printf 'x\ttouch GEHACKT').php"
R=0; lauf || R=$?; (cd "$W" && python3 deploy/dateien_sichern.py zurueckholen sicherungen/dateien >/dev/null 2>&1) || true; export R
ok "Dokumentname mit Tabulator und Befehl: als nicht lesbar gemeldet, Liste nur Kennung, Dokument und Ziel, nichts ausgeführt" '[ "$R" = 0 ] \
  && feld "$W/daten" meldung | grep -q "2 Dokument(e) nicht lesbar, Verweise darin nicht geprüft (kopie.php, .xttouch GEHACKT.php.)" \
  && [ -z "$(awk -F "\t" "NF != 3" "$W/sicherungen/.dateien-fehlend")" ] && ! grep -q "touch\|zz0000000000000000000z" "$W/sicherungen/.dateien-fehlend" && [ -z "$(find "$T" -name "GEHACKT*")" ]'
# Uhr zurückgestellt nach vielen Läufen am selben Tag (Release-Schleife): rotieren behält immer den laufenden Lauf
H=$(date -u +%Y-%m-%d); N=0; while [ "$N" -lt 40 ]; do alt "$(date -u -d "$H 20:00 UTC + $((N * 2)) min" +%Y-%m-%d_%H%M%S)" 2>/dev/null || true; N=$((N + 1)); done
export VERSATZ="$H 18:20 UTC"; R=0; uhr || R=$?; unset VERSATZ; export R H
ok "Uhr zurück, über 30 neuere Läufe am selben Tag: der laufende Lauf bleibt mit Archiv und Stand" '[ "$R" = 0 ] && [ "$(feld "$W/daten" ok)" = True ] \
  && [ "$(feld "$W/daten" datei)" = "daten-${H}_182000.tar.gz" ] && [ -f "$W/sicherungen/daten-${H}_182000.tar.gz" ] && [ -d "$W/sicherungen/dateien/${H}_182000" ]'
chmod -R u+rwx "$W" 2>/dev/null; rm -rf "$W"
# Getrennte Daten (ADR-007 Stufe 2): zweites Archiv intern-*.tar.gz für daten-intern/, gleich geprüft – Dateien und SQLite
for ART in dateien sqlite; do
  U="$T/u-$ART"
  mkdir -p "$U/deploy" "$U/regeln"; cp "$REPO"/deploy/sichern.sh "$REPO"/deploy/sicherung-pruefen.* "$REPO"/deploy/datenbank.py "$REPO"/deploy/daten_trennen.py "$REPO"/deploy/dateien_sichern.py "$U/deploy/"
  cp "$REPO/regeln/datenverantwortung.toml" "$U/regeln/"; cp -r "$REPO/tests/fixtures/data-seed" "$U/daten"
  printf '%s\n{"personen":[{"name":"Test Person"}]}' '<?php http_response_code(404); exit; ?>' > "$U/daten/hr-personal.php"
  mkdir -p "$U/daten/dateien/qs/ba"; printf 'Prüfbericht' > "$U/daten/dateien/qs/ba/ba00000000000000000001.bin"
  printf '%s\n{"liste":[{"id":"d1","dateien":[{"id":"ba00000000000000000001","groesse":12,"sha256":"%s"},{"id":"bb00000000000000000002","groesse":3,"sha256":"%s"}]}]}' \
    '<?php http_response_code(404); exit; ?>' "$(sha256sum "$U/daten/dateien/qs/ba/ba00000000000000000001.bin" | cut -c1-64)" "$(printf '0%.0s' $(seq 64))" > "$U/daten/qs-dokumente.php"
  [ "$ART" = sqlite ] && python3 "$U/deploy/datenbank.py" migrate "$U/daten" --offline >/dev/null
  sh "$U/deploy/sichern.sh" --jetzt >/dev/null
  VOR=$(ls -1d "$U"/sicherungen/dateien/2* | tail -1); export VOR
  python3 "$U/deploy/daten_trennen.py" trennen "$U/daten" "$U/daten-intern" --offline >/dev/null
  sleep 1; sh "$U/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?; export R U
  ST=$(basename "$U"/sicherungen/intern-*.tar.gz .tar.gz | cut -c8-); export ST
  ok "getrennt ($ART): zwei Archive derselben Zeit, beide geprüft" '[ "$R" = 0 ] && [ "$(feld "$U/daten" ok)" = True ] && [ -f "$U/sicherungen/daten-$ST.tar.gz" ] \
    && [ "$(ls "$U"/sicherungen/intern-*.tar.gz | wc -l)" = 1 ] && [ "$(feld "$U/daten" intern_datei)" = "intern-$ST.tar.gz" ]'
  mkdir "$U/r1" "$U/r2"; tar xzf "$U/sicherungen/daten-$ST.tar.gz" -C "$U/r1"; tar xzf "$U/sicherungen/intern-$ST.tar.gz" -C "$U/r2"
  if [ "$ART" = dateien ]; then
    ok "getrennt ($ART): Personaldaten nur im internen Archiv" '[ -f "$U/r2/hr-personal.php" ] && [ ! -e "$U/r1/hr-personal.php" ] && [ -f "$U/r1/angebot.php" ] && [ -f "$U/r2/.daten-intern" ] && [ -f "$U/r1/.daten-getrennt" ]'
  else
    ok "getrennt ($ART): Personaldaten nur in der internen Datenbank" 'python3 -c "import sqlite3,sys; a=sqlite3.connect(sys.argv[1]); b=sqlite3.connect(sys.argv[2]); n=lambda c: {r[0] for r in c.execute(\"SELECT name FROM documents\")}; sys.exit(0 if \"hr-personal\" in n(b) and \"hr-personal\" not in n(a) and \"angebot\" in n(a) else 1)" "$U/r1/.sqlite/store.sqlite" "$U/r2/.sqlite/store.sqlite"'
  fi
  ok "getrennt ($ART): Dateiablage aus daten-intern in derselben Reihe, über die Trennung hinweg fest verlinkt, Verweise aus dem internen Archiv geprüft" '[ "$(feld "$U/daten" ablage.anzahl)" = 1 ] \
    && [ "$(feld "$U/daten" ablage.neu)" = 0 ] && [ "$(stat -c %i "$U/sicherungen/dateien/$ST/qs/ba/ba00000000000000000001.bin")" = "$(stat -c %i "$VOR/qs/ba/ba00000000000000000001.bin")" ] \
    && [ "$(feld "$U/daten" ablage.fehlend)" = 1 ] && [ "$(cat "$U/sicherungen/.dateien-fehlend")" = "$(printf "bb00000000000000000002\tqs-dokumente\tfehlt in Ablage und Sicherung")" ]'
  ok "getrennt ($ART): Datensätze beider Bereiche gezählt" '[ "$(feld "$U/daten" datensaetze)" -ge 2 ] && [ "$(stat -c %a "$U"/sicherungen/intern-*.tar.gz)" = 600 ]'
  rm -f "$U/daten/.daten-getrennt"; sleep 1
  sh "$U/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?
  ok "getrennt ($ART): Kennzeichen in daten/ entfernt → Fehler statt Sicherung ohne interne Daten" '[ "$R" = 1 ] && [ "$(feld "$U/daten" ok)" = False ] \
    && grep -q "Kennzeichen" "$U/daten/sicherung.php" && [ "$(ls "$U"/sicherungen/intern-*.tar.gz | wc -l)" = 1 ]'
  printf '%s\n' "$(cat "$U/daten-intern/.daten-intern")" > "$U/daten/.daten-getrennt"
  mv "$U/daten-intern" "$U/weg"; sleep 1
  sh "$U/deploy/sichern.sh" --jetzt >/dev/null 2>&1 && R=0 || R=$?
  ok "getrennt ($ART): daten-intern fehlt → Fehler statt Sicherung ohne interne Daten" '[ "$R" = 1 ] && [ "$(feld "$U/daten" ok)" = False ] && grep -q "daten-intern" "$U/daten/sicherung.php"'
  chmod -R u+rwx "$U" 2>/dev/null; rm -rf "$U"
done
echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" -eq 0 ]
