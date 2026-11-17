#!/bin/sh
# Test von deploy/sicherung-extern.sh (externe Kopie der Datensicherung) in einem Wegwerf-Ordner – mit echtem restic gegen ein
# lokales Repository (WA_SICHERUNG_EXTERN_REPO) und über den SFTP-Weg des Betriebs (Attrappe für ssh, dahinter der echte
# sftp-server von OpenSSH); systemctl ist ein Platzhalter. Ohne restic bzw. sftp-server werden diese Teile übersprungen, in der
# CI sind sie Pflicht (WA_RESTIC_PFLICHT=1). Nicht geprüft: echte Storage Box, echtes ssh, systemd.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
I="$T/inst"; S="sh $I/deploy/sicherung-extern.sh"
mkdir -p "$T/bin" "$T/units" "$I/deploy" "$I/daten"
cp "$REPO/deploy/sicherung-extern.sh" "$I/deploy/"
printf '#!/bin/sh\necho "systemctl $*" >> "%s/aufrufe"\n[ "$1" != is-active ] || echo active\n' "$T" > "$T/bin/systemctl"
chmod +x "$T/bin/systemctl"
export WA_SYSTEMCTL="$T/bin/systemctl" WA_UNITS="$T/units" WA_OHNE_ROOT=1 WA_SICHERUNG_EXTERN_REPO="$T/repo" AUS CODE VORHER PW LETZTER
lauf() { AUS=$($S "$@" 2>&1) && CODE=0 || CODE=$?; }
# feld <schlüssel>: Wert aus dem Status (daten/sicherung-extern.php); scheitert, wenn die Datei kein gültiges JSON ist
feld() { python3 -c "import json, sys; t = open(sys.argv[1]).read(); print(json.loads(t[t.index(chr(10)) + 1:])[sys.argv[2]])" "$I/daten/sicherung-extern.php" "$1"; }
# Lokale Sicherungen wie von sichern.sh: Archive, zwei Stände der Dateiablage mit festem Verweis, Sperre und Reste eines Laufs
sicherungen_anlegen() {
  mkdir -p "$I/sicherungen/dateien/2026-11-15_023000/a" "$I/sicherungen/dateien/2026-11-16_023000/a" "$I/sicherungen/dateien/2026-11-17_023000.tmp"
  chmod 700 "$I/sicherungen"
  mkdir -p "$T/inhalt"; echo '{"angebot":1}' > "$T/inhalt/angebot.php"
  tar czf "$I/sicherungen/daten-2026-11-15_023000.tar.gz" -C "$T/inhalt" .
  echo '{"angebot":2}' > "$T/inhalt/angebot.php"
  tar czf "$I/sicherungen/daten-2026-11-16_023000.tar.gz" -C "$T/inhalt" .
  head -c 1048576 /dev/urandom > "$I/sicherungen/dateien/2026-11-15_023000/a/x.bin"
  ln "$I/sicherungen/dateien/2026-11-15_023000/a/x.bin" "$I/sicherungen/dateien/2026-11-16_023000/a/x.bin"
  : > "$I/sicherungen/.sperre"; echo halb > "$I/sicherungen/daten-2026-11-17_023000.tar.gz.tmp"; echo halb > "$I/sicherungen/dateien/2026-11-17_023000.tmp/y.bin"
  echo GEHEIM-AUSSERHALB > "$T/geheim"; ln -s "$T/geheim" "$I/sicherungen/verweis"
}
sicherungen_anlegen

lauf status
ok "status ohne Einrichtung: nicht eingerichtet, nichts angelegt" '[ $CODE = 0 ] && echo "$AUS" | grep -q "nicht eingerichtet" && [ -z "$(ls -A "$I" | grep "^\.sicherung-extern" || true)" ]'
lauf jetzt
ok "jetzt ohne Einrichtung: Abbruch ohne Status" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht eingerichtet" && [ ! -e "$I/daten/sicherung-extern.php" ]'
lauf einrichten
ok "einrichten ohne .env: Abbruch" '[ $CODE = 1 ] && echo "$AUS" | grep -q ".env nicht gefunden"'
: > "$I/.env"
AUS=$(WA_RESTIC="$T/bin/fehlt" $S einrichten 2>&1) && CODE=0 || CODE=$?
ok "einrichten ohne restic: Abbruch mit Hinweis, nichts erzeugt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "apt-get install restic" && [ ! -e "$I/.sicherung-extern-schluessel" ]'
lauf vielleicht
ok "unbekannter Befehl abgelehnt" '[ $CODE = 2 ]'
if [ "$(id -u)" != 0 ]; then
  AUS=$(WA_OHNE_ROOT='' $S status 2>&1) && CODE=0 || CODE=$?
  ok "ohne root: Abbruch" '[ $CODE = 1 ] && echo "$AUS" | grep -q "als root"'
fi

if ! command -v restic >/dev/null 2>&1 || ! command -v ssh-keygen >/dev/null 2>&1; then
  AUS=""; [ "${WA_RESTIC_PFLICHT:-}" != 1 ] || ok "restic und ssh-keygen verfügbar (WA_RESTIC_PFLICHT=1)" false
  echo "ÜBERSPRUNGEN: restic bzw. ssh-keygen fehlt – Einrichtung, Kopie, Prüfung und Aufbewahrung nicht getestet"
  echo "sicherung-extern.sh: $PASS bestanden, $FAIL fehlgeschlagen"
  [ "$FAIL" = 0 ]; exit
fi
echo "restic: $(restic version)"
# r: restic direkt am Test-Repository (zum Nachsehen und für rückdatierte Stände); ohne Zwischenspeicher, damit der Test
# nichts ins Heimatverzeichnis schreibt
r() { RESTIC_PASSWORD_FILE="$I/.sicherung-extern-passwort" restic --no-cache -r "$T/repo" "$@"; }
anzahl() { r snapshots --json | python3 -c 'import json, sys; print(len(json.load(sys.stdin) or []))'; }
kb() { find "$T/repo" -type f -printf '%s\n' | awk '{ s += $1 } END { print int(s / 1024) }'; }   # Summe der Dateien (du zählte 256 leere Ordner mit)

# ── Einrichtung ──
lauf einrichten
PW=$(cat "$I/.sicherung-extern-passwort")
ok "einrichten: Passwort (40 Zeichen) einmal angezeigt mit Hinweis, öffentlicher Schlüssel gezeigt" '[ $CODE = 0 ] && [ ${#PW} = 40 ] && echo "$AUS" | grep -qF "$PW" && echo "$AUS" | grep -q "außerhalb des Servers" && echo "$AUS" | grep -q "^ssh-ed25519 "'
ok "Schlüssel, Passwort und Zwischenspeicher nur für den Besitzer" '[ "$(stat -c %a "$I/.sicherung-extern-schluessel")" = 600 ] && [ "$(stat -c %a "$I/.sicherung-extern-passwort")" = 600 ] && ! grep -rqF "$PW" "$I/daten" "$I/sicherungen"'
ok "Repository angelegt, noch kein Status" '[ -f "$T/repo/config" ] && [ ! -e "$I/daten/sicherung-extern.php" ]'
ok "Timer: Installationsordner, täglich 03:30 nach der Sicherung, aktiviert" 'grep -q "ExecStart=/bin/sh $I/deploy/sicherung-extern.sh jetzt" "$T/units/wochenangebot-sicherung-extern.service" && grep -q "After=.*wochenangebot-sicherung.service" "$T/units/wochenangebot-sicherung-extern.service" && grep -q "OnCalendar=\*-\*-\* 03:30:00" "$T/units/wochenangebot-sicherung-extern.timer" && grep -q "systemctl enable --now wochenangebot-sicherung-extern.timer" "$T/aufrufe"'
VORHER=$(sha256sum "$I/.sicherung-extern-schluessel" "$I/.sicherung-extern-passwort")
lauf einrichten
ok "einrichten erneut: zerstört nichts, zeigt das Passwort nicht wieder" '[ $CODE = 0 ] && [ "$(sha256sum "$I/.sicherung-extern-schluessel" "$I/.sicherung-extern-passwort")" = "$VORHER" ] && ! echo "$AUS" | grep -qF "$PW" && echo "$AUS" | grep -q "Repository vorhanden"'

# ── Kopieren ──
lauf jetzt
ok "jetzt: Stand angelegt, Status ok mit Zeit, Anzahl und Größe" '[ $CODE = 0 ] && [ "$(feld ok)" = True ] && [ "$(feld staende)" = 1 ] && [ "$(feld groesse)" -gt 1000000 ] && feld letzter | grep -Eq "^20[0-9-]{8}T[0-9:]{8}Z$" && [ -z "$(feld meldung)" ]'
ok "Status für die Anwendung lesbar, ohne Passwort, Schlüssel und Ziel" '[ "$(stat -c %a "$I/daten/sicherung-extern.php")" = 644 ] && ! grep -qF -e "$PW" -e "$T/repo" -e ssh-ed25519 "$I/daten/sicherung-extern.php"'
r restore latest --target "$T/zurueck" >/dev/null
Z="$T/zurueck$I/sicherungen"
ok "Stand enthält die Archive byteweise gleich" 'cmp -s "$Z/daten-2026-11-15_023000.tar.gz" "$I/sicherungen/daten-2026-11-15_023000.tar.gz" && cmp -s "$Z/daten-2026-11-16_023000.tar.gz" "$I/sicherungen/daten-2026-11-16_023000.tar.gz"'
ok "ohne Sperre und Reste eines Laufs (*.tmp)" '[ ! -e "$Z/.sperre" ] && [ -z "$(find "$Z" -name "*.tmp")" ]'
ok "Stände der Dateiablage: fester Verweis bleibt einer, Inhalt nur einmal im Repository" '[ "$(stat -c %i "$Z/dateien/2026-11-15_023000/a/x.bin")" = "$(stat -c %i "$Z/dateien/2026-11-16_023000/a/x.bin")" ] && cmp -s "$Z/dateien/2026-11-16_023000/a/x.bin" "$I/sicherungen/dateien/2026-11-16_023000/a/x.bin" && [ "$(kb)" -lt 1300 ]'
ok "ein Verweis in sicherungen/ bleibt ein Verweis: Inhalt von außerhalb nicht in der Kopie" '[ -L "$Z/verweis" ] && ! grep -rq GEHEIM-AUSSERHALB "$T/zurueck"'
rm -rf "$T/zurueck"

lauf status
ok "status: Repository, Timer, letzter Lauf, Stände, Größe – ohne Sperre im Repository" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Timer: active" && echo "$AUS" | grep -q "Letzter Lauf: .*in Ordnung" && echo "$AUS" | grep -Eq "Stände: 1, neuester .* \(vor 0 Stunden\)" && echo "$AUS" | grep -Eq "Größe des Repositorys: [0-9]+ MB" && [ -z "$(ls "$T/repo/locks")" ] && [ "$(anzahl)" = 1 ]'

# ── Prüfung mit Rücksicherungsprobe ──
lauf pruefen
ok "pruefen: restic check und neuestes Archiv zurückgeholt, byteweise gleich; Arbeitsordner entfernt" '[ $CODE = 0 ] && echo "$AUS" | grep -q "daten-2026-11-16_023000.tar.gz zurückgeholt und byteweise gleich" && [ -z "$(ls -A "$I" | grep "arbeit" || true)" ] && [ "$(feld ok)" = True ]'
cp "$I/sicherungen/daten-2026-11-16_023000.tar.gz" "$T/original"; echo x >> "$I/sicherungen/daten-2026-11-16_023000.tar.gz"
lauf pruefen
ok "pruefen: abweichendes Archiv ergibt Fehler und Fehlerstatus" '[ $CODE = 1 ] && [ "$(feld ok)" = False ] && feld meldung | grep -q "weicht vom lokalen Original ab"'
cp "$T/original" "$I/sicherungen/daten-2026-11-16_023000.tar.gz"

# ── zweiter Lauf inkrementell ──
# Zahl der Stände am selben Tag hängt von der restic-Fassung ab (ab 0.13 bleibt neben dem neuesten auch der älteste, solange
# die Aufbewahrung nicht ausgeschöpft ist) – geprüft wird deshalb der neueste Stand und der Zuwachs
VORHER=$(kb); LETZTER=$(feld letzter); sleep 1
lauf jetzt
ok "zweiter Lauf ohne Änderung: neuer Stand, Repository wächst nur um Verwaltungsdaten" '[ $CODE = 0 ] && [ "$(feld letzter)" \> "$LETZTER" ] && [ "$(feld staende)" = "$(anzahl)" ] && [ $(($(kb) - VORHER)) -lt 100 ]'
head -c 524288 /dev/urandom > "$I/sicherungen/daten-2026-11-17_023000.tar.gz"
VORHER=$(kb)
lauf jetzt
ok "neues Archiv (512 KB): nur dieses kommt hinzu; mehrere Läufe am selben Tag belegen höchstens zwei Stände" '[ $CODE = 0 ] && [ "$(feld staende)" -le 2 ] && [ $(($(kb) - VORHER)) -gt 400 ] && [ $(($(kb) - VORHER)) -lt 700 ]'

# ── Aufbewahrung: rückdatierte Stände (täglich 36 Tage, danach alle 30 Tage bis 390 Tage) – nacheinander: gleichzeitige
# restic-Läufe stolpern über die Sperrdateien der anderen und wiederholen dann bis zu einer Minute lang ──
for D in $(seq 1 36) $(seq 60 30 390); do
  r backup -q --host stafl --time "$(date -u -d "$D days ago" '+%Y-%m-%d %H:%M:%S')" "$I/sicherungen" >/dev/null
done
VORHER=$(anzahl)
lauf jetzt
export AELTESTER; AELTESTER=$(r snapshots --json | python3 -c 'import json, sys; print(min(s["time"] for s in json.load(sys.stdin))[:10])')
ok "Aufbewahrung räumt: von $VORHER auf $(anzahl) Stände (30 Tage, 8 Wochen, 12 Monate), ältester rund ein Jahr alt" '[ $CODE = 0 ] && [ "$VORHER" -ge 49 ] && [ "$(anzahl)" -lt "$VORHER" ] && [ "$(anzahl)" -ge 30 ] && [ "$(anzahl)" -le 50 ] && [ "$(feld staende)" = "$(anzahl)" ] && [ "$AELTESTER" \< "$(date -u -d "300 days ago" +%Y-%m-%d)" ] && [ -z "$(feld meldung)" ]'
r check >/dev/null 2>&1 && CODE=0 || CODE=$?
ok "Repository nach dem Aufräumen in Ordnung (restic check)" '[ $CODE = 0 ]'

# ── Sperren ──
rm -f "$T/marke"; flock -x "$I/sicherungen/.sperre" sh -c "sleep 2; touch '$T/marke'" &
sleep 0.5
lauf jetzt
ok "laufende Datensicherung (Sperre von sichern.sh): externe Kopie wartet und läuft danach" '[ $CODE = 0 ] && [ -e "$T/marke" ]'
wait
VORHER=$(cat "$I/daten/sicherung-extern.php")
flock -x "$I/.sicherung-extern-passwort" sleep 3 &
sleep 0.5
lauf jetzt
ok "zweiter Lauf gleichzeitig: Abbruch, Status unverändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "läuft bereits" && [ "$(cat "$I/daten/sicherung-extern.php")" = "$VORHER" ]'
wait

# ── Fehlerfälle hinterlassen einen Fehlerstatus ──
AUS=$(WA_SICHERUNG_EXTERN_REPO="$T/nicht-da" $S jetzt 2>&1) && CODE=0 || CODE=$?
ok "Ziel nicht erreichbar: Rückgabewert 1, Fehlerstatus ohne Pfad des Ziels" '[ $CODE = 1 ] && [ "$(feld ok)" = False ] && feld meldung | grep -q "Übertragung fehlgeschlagen" && ! grep -q "nicht-da" "$I/daten/sicherung-extern.php"'
# restic-Attrappe: gibt für einen Unterbefehl einen vorgegebenen Code zurück (STUB_<befehl>) bzw. beendet das Skript (term)
cat > "$T/bin/restic" <<'EOF'
#!/bin/sh
for A in "$@"; do
  case "$A" in backup|forget)
    eval "RC=\${STUB_$A:-}"
    if [ "$RC" = term ]; then kill -TERM "$PPID"; sleep 2; exit 1; fi
    [ -z "$RC" ] || { [ "$RC" = 1 ] || restic "$@" >/dev/null 2>&1; exit "$RC"; } ;;
  esac
done
exec restic "$@"
EOF
chmod +x "$T/bin/restic"
AUS=$(WA_RESTIC="$T/bin/restic" STUB_backup=term $S jetzt 2>&1) && CODE=0 || CODE=$?
ok "Abbruch mitten im Lauf (Signal): Fehlerstatus Abbruch, Arbeitsordner entfernt" '[ $CODE != 0 ] && [ "$(feld ok)" = False ] && feld meldung | grep -q "Abbruch (Code" && [ -z "$(ls -A "$I" | grep -e arbeit -e "^\.status" || true)" ]'
AUS=$(WA_RESTIC="$T/bin/restic" STUB_backup=3 $S jetzt 2>&1) && CODE=0 || CODE=$?
ok "restic meldet unlesbare Dateien (Code 3): Stand angelegt, Status ok mit Warnung" '[ $CODE = 0 ] && [ "$(feld ok)" = True ] && feld meldung | grep -q "nicht lesbar"'
AUS=$(WA_RESTIC="$T/bin/restic" STUB_forget=1 $S jetzt 2>&1) && CODE=0 || CODE=$?
ok "Aufräumen scheitert: kopiert, Status ok mit Warnung" '[ $CODE = 0 ] && [ "$(feld ok)" = True ] && feld meldung | grep -q "Aufräumen alter Stände fehlgeschlagen"'
mv "$I/sicherungen" "$I/sicherungen.weg"; mkdir "$I/sicherungen"
lauf jetzt
ok "keine lokale Sicherung: Fehlerstatus, kein leerer Stand" '[ $CODE = 1 ] && [ "$(feld ok)" = False ] && feld meldung | grep -q "keine lokale Sicherung"'

# ── untergeschobene Verweise ──
VORHER=$(anzahl)
rmdir "$I/sicherungen"; mkdir "$T/fremd"; echo FREMD > "$T/fremd/daten-2026-01-01_000000.tar.gz"; ln -s "$T/fremd" "$I/sicherungen"
lauf jetzt
ok "Verweis statt sicherungen/: Fehlerstatus, nichts von außerhalb kopiert" '[ $CODE = 1 ] && feld meldung | grep -q "Verweis" && [ "$(anzahl)" = "$VORHER" ]'
rm "$I/sicherungen"; mv "$I/sicherungen.weg" "$I/sicherungen"
echo ORIGINAL > "$T/opfer"; chmod 600 "$T/opfer"
rm -f "$I/daten/sicherung-extern.php"; ln -s "$T/opfer" "$I/daten/sicherung-extern.php"
lauf jetzt
ok "Verweis statt der Statusdatei: ersetzt, Ziel des Verweises unverändert" '[ $CODE = 0 ] && [ "$(cat "$T/opfer")" = ORIGINAL ] && [ ! -L "$I/daten/sicherung-extern.php" ] && [ "$(feld ok)" = True ]'
VORHER=$(cat "$I/daten/sicherung-extern.php")
mv "$I/.sicherung-extern-schluessel" "$T/schluessel"; ln -s "$T/opfer" "$I/.sicherung-extern-schluessel"
lauf jetzt
ok "Verweis statt des Schlüssels: jetzt bricht ab, Ziel unverändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht eingerichtet" && [ "$(cat "$T/opfer")" = ORIGINAL ] && [ "$(cat "$I/daten/sicherung-extern.php")" = "$VORHER" ]'
lauf einrichten
ok "Verweis statt des Schlüssels: einrichten bricht ab, nichts überschrieben, nichts gezeigt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "keine echte Datei" && [ "$(cat "$T/opfer")" = ORIGINAL ] && ! echo "$AUS" | grep -q ORIGINAL'
rm "$I/.sicherung-extern-schluessel"; mv "$T/schluessel" "$I/.sicherung-extern-schluessel"
mv "$I/.sicherung-extern-passwort" "$T/passwort"; ln -s "$T/opfer" "$I/.sicherung-extern-passwort"
lauf einrichten
ok "Verweis statt des Passworts: einrichten bricht ab, nichts überschrieben, nichts gezeigt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "keine echte Datei" && [ "$(cat "$T/opfer")" = ORIGINAL ] && ! echo "$AUS" | grep -q ORIGINAL'
lauf pruefen
ok "Verweis statt des Passworts: pruefen bricht ab" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht eingerichtet"'
rm "$I/.sicherung-extern-passwort"; mv "$T/passwort" "$I/.sicherung-extern-passwort"

# ── beschädigtes Repository (zuletzt: danach ist es unbrauchbar) ──
for F in "$T/repo/data"/*/*; do truncate -s -1 "$F"; done
lauf pruefen
ok "pruefen: beschädigtes Repository ergibt Fehler und Fehlerstatus" '[ $CODE = 1 ] && [ "$(feld ok)" = False ] && feld meldung | grep -q "restic check"'

# ── aus ──
lauf aus
ok "aus: Timer entfernt, Repository, Schlüssel und Passwort bleiben" '[ $CODE = 0 ] && [ -z "$(ls "$T/units")" ] && grep -q "systemctl disable --now wochenangebot-sicherung-extern.timer" "$T/aufrufe" && [ -f "$T/repo/config" ] && [ -f "$I/.sicherung-extern-schluessel" ] && [ -f "$I/.sicherung-extern-passwort" ]'

# ── SFTP-Weg des Betriebs: Attrappe für ssh, dahinter der echte sftp-server ──
SFTPD=""
for F in /usr/lib/openssh/sftp-server /usr/libexec/openssh/sftp-server /usr/lib/ssh/sftp-server; do [ ! -x "$F" ] || SFTPD=$F; done
if [ -z "$SFTPD" ]; then
  AUS=""; [ "${WA_RESTIC_PFLICHT:-}" != 1 ] || ok "sftp-server verfügbar (WA_RESTIC_PFLICHT=1)" false
  echo "ÜBERSPRUNGEN: sftp-server fehlt – SFTP-Weg nicht getestet"
else
  unset WA_SICHERUNG_EXTERN_REPO
  J="$T/inst2"; S="sh $J/deploy/sicherung-extern.sh"; I=$J
  mkdir -p "$J/deploy" "$J/daten" "$T/box"; cp "$REPO/deploy/sicherung-extern.sh" "$J/deploy/"
  sicherungen_anlegen
  printf '#!/bin/sh\necho "ssh $*" >> "%s/ssh-aufrufe"\n[ ! -e "%s/box-weg" ] || exit 255\nexec %s -d "%s/box"\n' "$T" "$T" "$SFTPD" "$T" > "$T/bin/ssh"
  chmod +x "$T/bin/ssh"
  export WA_SSH="$T/bin/ssh"
  for Z in "" "-oProxyCommand=x@box.example" "benutzer@box.example;id" "benutzer box.example"; do
    echo "SICHERUNG_EXTERN_ZIEL=$Z" > "$J/.env"
    lauf einrichten
    ok "Ziel <$Z> abgelehnt: nichts erzeugt, keine Verbindung" '[ $CODE = 1 ] && echo "$AUS" | grep -q "SICHERUNG_EXTERN_ZIEL=<Benutzer>@<Benutzer>.your-storagebox.de" && [ ! -e "$J/.sicherung-extern-schluessel" ] && [ ! -e "$T/ssh-aufrufe" ]'
  done
  echo "SICHERUNG_EXTERN_ZIEL=benutzer-sub1@box.example" > "$J/.env"
  touch "$T/box-weg"
  lauf einrichten
  ok "SFTP: Schlüssel noch nicht hinterlegt (keine Verbindung): Befehl zum Hinterlegen gezeigt, kein Timer, erneut ausführbar" '[ $CODE = 1 ] && echo "$AUS" | grep -q "cat $J/.sicherung-extern-schluessel.pub | ssh -p 23 -o UserKnownHostsFile=$J/.sicherung-extern-hosts benutzer-sub1@box.example install-ssh-key" && echo "$AUS" | grep -q "Danach erneut" && [ -z "$(ls "$T/units")" ]'
  PW=$(cat "$J/.sicherung-extern-passwort")
  rm "$T/box-weg"
  echo "[box.example]:23 $(cut -d' ' -f1,2 "$J/.sicherung-extern-schluessel.pub")" > "$J/.sicherung-extern-hosts"   # was das echte ssh beim ersten Kontakt merkt
  lauf einrichten
  ok "SFTP: zweiter Aufruf legt das Repository im Ordner wochenangebot an, Passwort nicht erneut gezeigt, Fingerabdruck der Gegenstelle gezeigt" '[ $CODE = 0 ] && [ -f "$T/box/wochenangebot/config" ] && ! echo "$AUS" | grep -qF "$PW" && [ -n "$(ls "$T/units")" ] && echo "$AUS" | grep -q "SHA256:.*box.example"'
  ok "SFTP: ssh mit Port 23, eigenem Schlüssel, gemerkter Gegenstelle, ohne Passwortabfrage" 'grep -q -- "-F /dev/null -p 23 -i $J/.sicherung-extern-schluessel -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$J/.sicherung-extern-hosts .* benutzer-sub1@box.example -s sftp$" "$T/ssh-aufrufe"'
  lauf jetzt
  ok "SFTP: jetzt kopiert, Status ok ohne Namen der Gegenstelle" '[ $CODE = 0 ] && [ "$(feld ok)" = True ] && [ "$(feld staende)" = 1 ] && ! grep -q "box.example" "$J/daten/sicherung-extern.php"'
  lauf pruefen
  ok "SFTP: pruefen holt das neueste Archiv zurück, byteweise gleich" '[ $CODE = 0 ] && echo "$AUS" | grep -q "byteweise gleich"'
  lauf status
  ok "SFTP: status zeigt Ziel und Stände" '[ $CODE = 0 ] && echo "$AUS" | grep -q "sftp:benutzer-sub1@box.example:wochenangebot" && echo "$AUS" | grep -q "Stände: 1"'
  touch "$T/box-weg"
  lauf jetzt
  ok "SFTP: Storage Box nicht erreichbar: Rückgabewert 1, Fehlerstatus ohne Namen der Gegenstelle" '[ $CODE = 1 ] && [ "$(feld ok)" = False ] && feld meldung | grep -q "Übertragung fehlgeschlagen" && ! grep -q "box.example" "$J/daten/sicherung-extern.php"'
  lauf status
  ok "SFTP: status bei nicht erreichbarer Storage Box: letzter Lauf mit Fehler, Rückgabewert 1" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Letzter Lauf: .*FEHLER" && echo "$AUS" | grep -q "nicht erreichbar"'
fi
echo "sicherung-extern.sh: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
