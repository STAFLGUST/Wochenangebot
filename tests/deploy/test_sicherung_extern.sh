#!/bin/sh
# Test von deploy/sicherung-extern.sh (externe Kopie der Datensicherung) in einem Wegwerf-Ordner – mit echtem restic gegen ein
# lokales Repository (WA_SICHERUNG_EXTERN_REPO) und über den SFTP-Weg des Betriebs (Attrappe für ssh, dahinter der echte
# sftp-server von OpenSSH); systemctl ist ein Platzhalter. Ohne restic bzw. sftp-server werden diese Teile übersprungen, in der
# CI sind sie Pflicht (WA_RESTIC_PFLICHT=1). Passwortwechsel (passwort-neu) mit Fehlern und Abbrüchen in jedem Schritt über
# eine zweite restic-Attrappe. Nicht geprüft: echte Storage Box, echtes ssh, systemd.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"' EXIT
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
lauf passwort-neu
ok "passwort-neu ohne Einrichtung: Abbruch, nichts angelegt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht eingerichtet" && [ -z "$(ls -A "$I" | grep "^\.sicherung-extern" || true)" ]'
lauf einrichten
ok "einrichten ohne .env: Abbruch" '[ $CODE = 1 ] && echo "$AUS" | grep -q ".env nicht gefunden"'
: > "$I/.env"
AUS=$(WA_RESTIC="$T/bin/fehlt" $S einrichten 2>&1) && CODE=0 || CODE=$?
ok "einrichten ohne restic: Abbruch mit Hinweis, nichts erzeugt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "apt-get install restic" && [ ! -e "$I/.sicherung-extern-schluessel" ]'
lauf vielleicht
ok "unbekannter Befehl abgelehnt" '[ $CODE = 2 ]'
mkdir -p "$T/mit leer/deploy"; cp "$REPO/deploy/sicherung-extern.sh" "$T/mit leer/deploy/"
AUS=$(sh "$T/mit leer/deploy/sicherung-extern.sh" status 2>&1) && CODE=0 || CODE=$?
ok "Installationsordner mit Leerzeichen (stünde ungeschützt in Unit und sftp.command): Abbruch mit klarer Meldung" '[ $CODE = 1 ] && echo "$AUS" | grep -q "enthält Leerzeichen oder Sonderzeichen"'
flock -x "$I/.env" sleep 2 &
sleep 0.5
lauf einrichten
ok "einrichten zweimal gleichzeitig: Abbruch, weder Schlüssel noch Passwort erzeugt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "einrichten läuft bereits" && [ -z "$(ls -A "$I" | grep "^\.sicherung-extern" || true)" ]'
wait
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
ok "einrichten: Passwort (40 Zeichen) einmal angezeigt mit Hinweis, öffentlicher Schlüssel gezeigt" '[ $CODE = 0 ] && [ ${#PW} = 40 ] && echo "$AUS" | grep -qF "$PW" && echo "$AUS" | grep -q "außerhalb des Servers" && echo "$AUS" | grep -q "nicht kopieren oder weitergeben" && echo "$AUS" | grep -q "^ssh-ed25519 "'
ok "Schlüssel, Passwort und Zwischenspeicher nur für den Besitzer" '[ "$(stat -c %a "$I/.sicherung-extern-schluessel")" = 600 ] && [ "$(stat -c %a "$I/.sicherung-extern-passwort")" = 600 ] && ! grep -rqF "$PW" "$I/daten" "$I/sicherungen"'
ok "Repository angelegt, noch kein Status" '[ -f "$T/repo/config" ] && [ ! -e "$I/daten/sicherung-extern.php" ]'
ok "Timer: Installationsordner, täglich 03:30 nach der Sicherung, aktiviert" 'grep -q "ExecStart=/bin/sh $I/deploy/sicherung-extern.sh jetzt" "$T/units/wochenangebot-sicherung-extern.service" && grep -q "After=.*wochenangebot-sicherung.service" "$T/units/wochenangebot-sicherung-extern.service" && grep -q "OnCalendar=\*-\*-\* 03:30:00" "$T/units/wochenangebot-sicherung-extern.timer" && grep -q "systemctl enable --now wochenangebot-sicherung-extern.timer" "$T/aufrufe"'
VORHER=$(sha256sum "$I/.sicherung-extern-schluessel" "$I/.sicherung-extern-passwort")
lauf einrichten
ok "einrichten erneut: zerstört nichts, zeigt das Passwort nicht wieder" '[ $CODE = 0 ] && [ "$(sha256sum "$I/.sicherung-extern-schluessel" "$I/.sicherung-extern-passwort")" = "$VORHER" ] && ! echo "$AUS" | grep -qF "$PW" && echo "$AUS" | grep -q "Repository vorhanden"'

# ── Kopieren ──
lauf jetzt
ok "jetzt: Stand angelegt, Status ok mit Zeit, Anzahl und Größe" '[ $CODE = 0 ] && [ "$(feld ok)" = True ] && [ "$(feld staende)" = 1 ] && [ "$(feld groesse)" -gt 1000000 ] && feld letzter | grep -Eq "^20[0-9-]{8}T[0-9:]{8}Z$" && [ -z "$(feld meldung)" ]'
export ABSTAND; ABSTAND=$(($(date -d "$(r snapshots --json | python3 -c 'import json, sys; print(json.load(sys.stdin)[0]["time"])')" +%s) - $(date -d "$(feld letzter)" +%s)))
ok "Zeit im Status ist die des eben angelegten Stands (restic liegt $ABSTAND s dahinter)" '[ "$ABSTAND" -ge 0 ] && [ "$ABSTAND" -le 30 ]'
ok "Status für die Anwendung lesbar, ohne Passwort, Schlüssel und Ziel" '[ "$(stat -c %a "$I/daten/sicherung-extern.php")" = 644 ] && ! grep -qF -e "$PW" -e "$T/repo" -e ssh-ed25519 "$I/daten/sicherung-extern.php"'
r restore latest --target "$T/zurueck" >/dev/null
Z="$T/zurueck$I/sicherungen"
ok "Stand enthält die Archive byteweise gleich" 'cmp -s "$Z/daten-2026-11-15_023000.tar.gz" "$I/sicherungen/daten-2026-11-15_023000.tar.gz" && cmp -s "$Z/daten-2026-11-16_023000.tar.gz" "$I/sicherungen/daten-2026-11-16_023000.tar.gz"'
ok "ohne Sperre und Reste eines Laufs (*.tmp)" '[ ! -e "$Z/.sperre" ] && [ -z "$(find "$Z" -name "*.tmp")" ]'
ok "Stände der Dateiablage: fester Verweis bleibt einer, Inhalt nur einmal im Repository" '[ "$(stat -c %i "$Z/dateien/2026-11-15_023000/a/x.bin")" = "$(stat -c %i "$Z/dateien/2026-11-16_023000/a/x.bin")" ] && cmp -s "$Z/dateien/2026-11-16_023000/a/x.bin" "$I/sicherungen/dateien/2026-11-16_023000/a/x.bin" && [ "$(kb)" -lt 1300 ]'
ok "ein Verweis in sicherungen/ bleibt ein Verweis: Inhalt von außerhalb nicht in der Kopie" '[ -L "$Z/verweis" ] && ! grep -rq GEHEIM-AUSSERHALB "$T/zurueck"'
rm -rf "$T/zurueck"

lauf status
ok "status: Repository, Timer, Stände, Größe – ohne Sperre im Repository" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Timer: active" && echo "$AUS" | grep -Eq "Stände: 1, neuester .* \(vor 0 Stunden\)" && echo "$AUS" | grep -Eq "Größe des Repositorys: [0-9]+ MB" && [ -z "$(ls "$T/repo/locks")" ] && [ "$(anzahl)" = 1 ]'

# ── Prüfung mit Rücksicherungsprobe ──
VORHER=$(cat "$I/daten/sicherung-extern.php")
lauf pruefen
ok "pruefen: restic check und neuestes Archiv zurückgeholt, byteweise gleich; Arbeitsordner entfernt, Status unverändert" '[ $CODE = 0 ] && echo "$AUS" | grep -q "daten-2026-11-16_023000.tar.gz zurückgeholt und byteweise gleich" && [ -z "$(ls -A "$I" | grep "arbeit" || true)" ] && [ "$(cat "$I/daten/sicherung-extern.php")" = "$VORHER" ]'
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

# ── Passwort wechseln ──
# alt: restic mit dem bisherigen Passwort; schluessel: Zahl der Schlüssel im Repository; reste: Zwischendateien und Arbeitsordner
P="$I/.sicherung-extern-passwort"
cp "$P" "$T/pw-alt"; cp -r "$T/repo/keys" "$T/keys-alt"
alt() { RESTIC_PASSWORD_FILE="$T/pw-alt" restic --no-cache -r "$T/repo" "$@" >/dev/null 2>&1; }
schluessel() { find "$T/repo/keys" -type f | wc -l; }
reste() { find "$I" -maxdepth 1 \( -name '.sicherung-extern-neu*' -o -name '.sicherung-extern-arbeit*' \); }
VORHER=$(cat "$I/daten/sicherung-extern.php")
flock -x "$P" sleep 3 &
sleep 0.5
lauf passwort-neu
ok "passwort-neu, während ein Lauf die Sperre hält: Abbruch mit Hinweis (später erneut), nichts geändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "läuft bereits – später erneut" && cmp -s "$P" "$T/pw-alt" && [ "$(schluessel)" = 1 ] && [ -z "$(reste)" ]'
wait
flock -x "$I/.env" sleep 3 &
sleep 0.5
lauf passwort-neu
ok "passwort-neu, während einrichten läuft: Abbruch, nichts geändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "einrichten läuft – später erneut" && cmp -s "$P" "$T/pw-alt" && [ "$(schluessel)" = 1 ] && [ -z "$(reste)" ]'
wait
AUS=$(WA_SICHERUNG_EXTERN_REPO="$T/nicht-da" $S passwort-neu 2>&1) && CODE=0 || CODE=$?
ok "passwort-neu, Repository nicht erreichbar: Abbruch, Passwortdatei und Status unverändert, keine Zwischendatei, das bisherige Passwort öffnet das Repository" '[ $CODE = 1 ] && echo "$AUS" | grep -q "es gilt weiter das bisherige" && cmp -s "$P" "$T/pw-alt" && [ "$(cat "$I/daten/sicherung-extern.php")" = "$VORHER" ] && [ -z "$(reste)" ] && alt cat config'
# restic-Attrappe für den Wechsel: „restic <STUB_FEHLER>“ scheitert, statt zu laufen; nach „restic <STUB_ABBRUCH>“ wird das
# Skript beendet (Abbruch genau nach diesem Schritt); STUB_VERWEIS: während der Probe mit dem neuen Passwort wird die
# Passwortdatei durch einen Verweis auf STUB_OPFER ersetzt; STUB_LAUF: Befehl, der nach dem Umbenennen (vor „key list“) läuft
cat > "$T/bin/restic-wechsel" <<'EOF'
#!/bin/sh
case " $* " in
  *" ${STUB_FEHLER:-keiner} "*) exit 1 ;;
  *" ${STUB_ABBRUCH:-keiner} "*) restic "$@"; kill -TERM "$PPID"; sleep 2; exit 1 ;;
  *" key list "*) [ -z "${STUB_LAUF:-}" ] || $STUB_LAUF > "$STUB_OPFER.lauf" 2>&1 ;;
esac
[ -z "${STUB_VERWEIS:-}" ] || case "$RESTIC_PASSWORD_FILE" in *-neu.*) rm -f "$STUB_VERWEIS"; ln -s "$STUB_OPFER" "$STUB_VERWEIS" ;; esac
exec restic "$@"
EOF
chmod +x "$T/bin/restic-wechsel"
AUS=$(WA_RESTIC="$T/bin/restic-wechsel" STUB_FEHLER="key add" $S passwort-neu 2>&1) && CODE=0 || CODE=$?
ok "neuer Schlüssel lässt sich nicht anlegen: alles beim Alten, Zwischendatei entfernt, Status unverändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "es gilt weiter das bisherige" && cmp -s "$P" "$T/pw-alt" && [ "$(schluessel)" = 1 ] && [ -z "$(reste)" ] && [ "$(cat "$I/daten/sicherung-extern.php")" = "$VORHER" ]'
AUS=$(WA_RESTIC="$T/bin/restic-wechsel" STUB_ABBRUCH="key add" $S passwort-neu 2>&1) && CODE=0 || CODE=$?
ok "Abbruch nach dem Anlegen des neuen Schlüssels: Passwortdatei unverändert und gültig, Zwischendatei entfernt, kein Passwort gezeigt, Status unverändert" '[ $CODE != 0 ] && cmp -s "$P" "$T/pw-alt" && alt cat config && [ "$(schluessel)" = 2 ] && [ -z "$(reste)" ] && ! echo "$AUS" | grep -q "Passwort des Repositorys" && [ "$(cat "$I/daten/sicherung-extern.php")" = "$VORHER" ]'
AUS=$(WA_RESTIC="$T/bin/restic-wechsel" STUB_FEHLER="cat config" $S passwort-neu 2>&1) && CODE=0 || CODE=$?
ok "Probe mit dem neuen Passwort scheitert: alles beim Alten, Zwischendatei entfernt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Probe mit dem neuen Passwort gescheitert" && cmp -s "$P" "$T/pw-alt" && alt cat config && [ "$(schluessel)" = 3 ] && [ -z "$(reste)" ]'
AUS=$(WA_RESTIC="$T/bin/restic-wechsel" STUB_FEHLER="key remove" $S passwort-neu 2>&1) && CODE=0 || CODE=$?
ok "bisheriger Schlüssel lässt sich nicht entfernen: neues Passwort hinterlegt und gültig, aber nicht gezeigt; das bisherige gilt noch" '[ $CODE = 1 ] && echo "$AUS" | grep -q "das bisherige gilt noch" && ! cmp -s "$P" "$T/pw-alt" && ! echo "$AUS" | grep -qF "$(cat "$P")" && r cat config >/dev/null && alt cat config && [ -z "$(reste)" ]'
cp "$P" "$T/pw-zwischen"
AUS=$(WA_RESTIC="$T/bin/restic-wechsel" STUB_ABBRUCH="key list" $S passwort-neu 2>&1) && CODE=0 || CODE=$?
ok "Abbruch zwischen Umbenennen und Entfernen der alten Schlüssel: nicht ausgesperrt – die Passwortdatei öffnet das Repository, nichts gezeigt, Status unverändert" '[ $CODE != 0 ] && ! cmp -s "$P" "$T/pw-zwischen" && ! echo "$AUS" | grep -qF "$(cat "$P")" && r cat config >/dev/null && [ -f "$P" ] && [ ! -L "$P" ] && [ "$(stat -c %a "$P")" = 600 ] && [ -z "$(reste)" ] && [ "$(cat "$I/daten/sicherung-extern.php")" = "$VORHER" ]'
lauf jetzt
ok "jetzt nach einem abgebrochenen Wechsel: läuft mit der Passwortdatei" '[ $CODE = 0 ] && [ "$(feld ok)" = True ]'
# Sperre eines abgebrochenen restic-Laufs im Repository: restic hängt an einer vollen FIFO und wird hart beendet
mkfifo "$T/voll"; exec 5<>"$T/voll"
RESTIC_PASSWORD_FILE="$P" restic --no-cache -r "$T/repo" dump latest "$I/sicherungen/dateien/2026-11-16_023000/a/x.bin" > "$T/voll" 2>/dev/null &
for _ in $(seq 50); do [ -z "$(ls "$T/repo/locks")" ] || break; sleep 0.2; done
kill -9 $!; wait; exec 5>&-
export SPERREN; SPERREN=$(find "$T/repo/locks" -type f | wc -l)
VORHER=$(cat "$I/daten/sicherung-extern.php")
echo ORIGINAL > "$T/opfer"; echo REST > "$I/.sicherung-extern-neu.rest"   # Zwischendatei eines hart beendeten Wechsels
AUS=$(WA_RESTIC="$T/bin/restic-wechsel" STUB_VERWEIS="$P" STUB_OPFER="$T/opfer" STUB_LAUF="$S jetzt" $S passwort-neu 2>&1) && CODE=0 || CODE=$?
PW=$(cat "$P")
ok "passwort-neu gelingt, auch nach abgebrochenen Wechseln und mit der Sperre eines abgebrochenen Laufs ($SPERREN) im Repository: neues Passwort (40 Zeichen) genau einmal gezeigt, mit Hinweisen" '[ $CODE = 0 ] && [ "$SPERREN" = 1 ] && [ ${#PW} = 40 ] && [ "$(echo "$AUS" | grep -cF "$PW")" = 1 ] && echo "$AUS" | grep -q "Das bisherige Passwort gilt nicht mehr" && echo "$AUS" | grep -q "außerhalb des Servers" && echo "$AUS" | grep -q "nicht kopieren oder weitergeben" && ! echo "$AUS" | grep -qF -e "$(cat "$T/pw-alt")" -e "$(cat "$T/pw-zwischen")"'
ok "danach öffnet nur noch das neue Passwort das Repository: ein Schlüssel, das bisherige und die der abgebrochenen Wechsel gelten nicht mehr" 'r cat config >/dev/null && ! alt cat config && ! RESTIC_PASSWORD_FILE="$T/pw-zwischen" restic --no-cache -r "$T/repo" cat config >/dev/null 2>&1 && [ "$(schluessel)" = 1 ]'
ok "Verweis, der während des Wechsels an die Stelle der Passwortdatei gelegt wird: ersetzt, Ziel unverändert; Passwortdatei nur für den Besitzer, Status unverändert, keine Zwischendatei (auch die eines hart beendeten Wechsels ist entfernt)" '[ "$(cat "$T/opfer")" = ORIGINAL ] && [ -f "$P" ] && [ ! -L "$P" ] && [ "$(stat -c %a "$P")" = 600 ] && [ "$(cat "$I/daten/sicherung-extern.php")" = "$VORHER" ] && [ -z "$(reste)" ] && ! grep -rqF "$PW" "$I/daten" "$I/sicherungen"'
ok "jetzt, das während des Wechsels nach dem Umbenennen startet: abgelehnt (die Sperre liegt auch auf der neuen Passwortdatei)" 'grep -q "läuft bereits" "$T/opfer.lauf"'
lauf jetzt
ok "jetzt nach dem Wechsel: Stand angelegt, Status ok" '[ $CODE = 0 ] && [ "$(feld ok)" = True ] && [ "$(feld staende)" = "$(anzahl)" ]'
lauf status
ok "status nach dem Wechsel" '[ $CODE = 0 ] && echo "$AUS" | grep -Eq "Stände: [0-9]+, neuester "'
lauf pruefen
ok "pruefen nach dem Wechsel: Archiv zurückgeholt, byteweise gleich" '[ $CODE = 0 ] && echo "$AUS" | grep -q "byteweise gleich"'
# Aufbewahrte Kopie prüfen (vor dem Vernichten des alten Ausdrucks): verdeckt eingelesen, nie ausgegeben, ändert nichts
cp "$P" "$T/pw-vor-pruefen"
AUS=$(printf '  %s \r\n' "$(cat "$P")" | $S passwort-pruefen 2>&1) && CODE=0 || CODE=$?
ok "passwort-pruefen mit dem richtigen Passwort (auch mit Leerzeichen vom Einfügen): Stimmt, Passwort nicht ausgegeben, nichts geändert" '[ $CODE = 0 ] && echo "$AUS" | grep -q "^Stimmt: " && ! echo "$AUS" | grep -qF "$(cat "$P")" && cmp -s "$P" "$T/pw-vor-pruefen" && [ "$(schluessel)" = 1 ]'
AUS=$(printf '%sx\n' "$(cat "$P")" | $S passwort-pruefen 2>&1) && CODE=0 || CODE=$?
ok "passwort-pruefen mit einem Tippfehler: stimmt nicht, Code 1, Passwort nicht ausgegeben" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Stimmt NICHT" && ! echo "$AUS" | grep -qF "$(cat "$P")"'
AUS=$(cat "$T/pw-alt" | $S passwort-pruefen 2>&1) && CODE=0 || CODE=$?
ok "passwort-pruefen mit dem bisherigen Passwort bzw. leerer Eingabe: stimmt nicht" '[ $CODE = 1 ] && ! printf "" | $S passwort-pruefen >/dev/null 2>&1'
# Grenze des Wechsels (steht so in der Anleitung): der Hauptschlüssel bleibt derselbe. Eine Schlüsseldatei von vor dem Wechsel –
# wie sie in einem älteren Snapshot der Storage Box liegt – öffnet mit dem alten Passwort auch Stände von nach dem Wechsel
cp "$T/keys-alt"/* "$T/repo/keys/"
ok "Grenze: alte Schlüsseldatei und altes Passwort öffnen auch den Stand von nach dem Wechsel" 'alt ls latest'
for F in "$T/keys-alt"/*; do rm -f "$T/repo/keys/${F##*/}"; done
ok "Gegenprobe: ohne die alte Schlüsseldatei öffnet das alte Passwort nichts" '! alt ls latest && [ "$(schluessel)" = 1 ]'

# ── Fehlerfälle hinterlassen einen Fehlerstatus ──
AUS=$(WA_SICHERUNG_EXTERN_REPO="$T/nicht-da" $S jetzt 2>&1) && CODE=0 || CODE=$?
ok "Ziel nicht erreichbar: Rückgabewert 1, Fehlerstatus ohne Pfad des Ziels" '[ $CODE = 1 ] && [ "$(feld ok)" = False ] && feld meldung | grep -q "Übertragung fehlgeschlagen" && ! grep -q "nicht-da" "$I/daten/sicherung-extern.php"'
VORHER=$(cat "$I/daten/sicherung-extern.php")
lauf pruefen
ok "pruefen nach gescheitertem jetzt: Prüfung besteht, der Fehlerstatus bleibt stehen" '[ $CODE = 0 ] && echo "$AUS" | grep -q "byteweise gleich" && [ "$(cat "$I/daten/sicherung-extern.php")" = "$VORHER" ] && [ "$(feld ok)" = False ]'
# restic-Attrappe: gibt für einen Unterbefehl einen vorgegebenen Code zurück (STUB_<befehl>), beendet das Skript (term) oder
# verhält sich wie ein sichern.sh, das mitten im Lauf startet (sperre): hält dessen Sperre 4 Sekunden und merkt sich den
# Status, wie er kurz vor dem Loslassen aussah
cat > "$T/bin/restic" <<'EOF'
#!/bin/sh
for A in "$@"; do
  case "$A" in backup|forget)
    eval "RC=\${STUB_$A:-}"
    if [ "$RC" = term ]; then kill -TERM "$PPID"; sleep 2; exit 1; fi
    if [ "$RC" = sperre ]; then
      flock -x "$STUB_I/sicherungen/.sperre" sh -c 'sleep 4; cp "$STUB_I/daten/sicherung-extern.php" "$STUB_I/waehrend"' >/dev/null 2>&1 &
      sleep 0.5; exec restic "$@"
    fi
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
VORHER=$(cat "$I/daten/sicherung-extern.php")
AUS=$(WA_RESTIC="$T/bin/restic" STUB_backup=sperre STUB_I="$I" $S jetzt 2>&1) && CODE=0 || CODE=$?
ok "Datensicherung startet während der Übertragung: Status erst ersetzt, wenn ihre Sperre frei ist (ihr tar läse die Datei sonst im Wechsel)" '[ $CODE = 0 ] && [ "$(cat "$I/waehrend")" = "$VORHER" ] && [ "$(feld ok)" = True ] && [ -z "$(feld meldung)" ]'
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
printf '%s\n%s' '<?php http_response_code(404); exit; ?>' '{"t":"2026-11-17T03:40:00Z","ok":false,"meldung":"GEFAELSCHT"}' > "$I/daten/sicherung-extern.php"
lauf status
ok "status zeigt nichts aus der Statusdatei (im Container beschreibbar): Angaben nur aus dem Repository" '[ $CODE = 0 ] && echo "$AUS" | grep -Eq "Stände: [0-9]+, neuester " && ! echo "$AUS" | grep -q GEFAELSCHT'
rm -f "$I/daten/sicherung-extern.php"; mkfifo "$I/daten/sicherung-extern.php"
AUS=$(timeout 120 $S status 2>&1) && CODE=0 || CODE=$?
ok "FIFO statt der Statusdatei: status bleibt nicht hängen" '[ $CODE = 0 ] && echo "$AUS" | grep -Eq "Stände: [0-9]+, neuester "'
rm -f "$I/daten/sicherung-extern.php"; ln -s /dev/zero "$I/daten/sicherung-extern.php"
AUS=$(timeout 120 $S status 2>&1) && CODE=0 || CODE=$?
ok "Verweis auf /dev/zero statt der Statusdatei: status liest ihn nicht" '[ $CODE = 0 ] && echo "$AUS" | grep -Eq "Stände: [0-9]+, neuester "'
rm -f "$I/daten/sicherung-extern.php"; mkfifo "$I/daten/sicherung-extern.php"
lauf jetzt
ok "FIFO statt der Statusdatei: jetzt ersetzt sie durch eine echte Datei" '[ $CODE = 0 ] && [ -f "$I/daten/sicherung-extern.php" ] && [ "$(feld ok)" = True ]'
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
lauf passwort-neu
ok "Verweis statt des Passworts: passwort-neu bricht ab, Ziel und Repository unverändert" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht eingerichtet" && [ "$(cat "$T/opfer")" = ORIGINAL ] && [ "$(schluessel)" = 1 ] && [ -z "$(reste)" ]'
rm "$I/.sicherung-extern-passwort"; mv "$T/passwort" "$I/.sicherung-extern-passwort"

# ── Uhr war einmal vorgestellt: ein Stand aus der Zukunft bleibt der neueste im Repository ──
r backup -q --host stafl --time "$(date -u -d '2 days' '+%Y-%m-%d %H:%M:%S')" "$I/sicherungen" >/dev/null
lauf jetzt
ok "Stand aus der Zukunft im Repository: Status nennt die Zeit des eigenen Laufs, nicht die des neuesten Stands" '[ $CODE = 0 ] && [ "$(feld ok)" = True ] && ! [ "$(feld letzter)" \> "$(date -u +%Y-%m-%dT%H:%M:%SZ)" ] && [ "$(feld letzter)" \> "$(date -u -d "5 minutes ago" +%Y-%m-%dT%H:%M:%SZ)" ]'

# ── beschädigtes Repository (zuletzt: danach ist es unbrauchbar) ──
for F in "$T/repo/data"/*/*; do chmod u+w "$F"; truncate -s -1 "$F"; done   # restic legt die Dateien nur lesbar an
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
  ok "SFTP: zweiter Aufruf legt das Repository im Ordner wochenangebot an, Passwort nicht erneut gezeigt, Fingerabdruck der Gegenstelle gezeigt (vergleichen, bevor das Passwort der Storage Box getippt wird)" '[ $CODE = 0 ] && [ -f "$T/box/wochenangebot/config" ] && ! echo "$AUS" | grep -qF "$PW" && [ -n "$(ls "$T/units")" ] && echo "$AUS" | grep -q "SHA256:.*box.example" && echo "$AUS" | grep -q "BEVOR das Passwort"'
  ok "SFTP: ssh mit Port 23, eigenem Schlüssel, gemerkter Gegenstelle, ohne Passwortabfrage" 'grep -q -- "-F /dev/null -p 23 -i $J/.sicherung-extern-schluessel -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$J/.sicherung-extern-hosts .* benutzer-sub1@box.example -s sftp$" "$T/ssh-aufrufe"'
  lauf jetzt
  ok "SFTP: jetzt kopiert, Status ok ohne Namen der Gegenstelle" '[ $CODE = 0 ] && [ "$(feld ok)" = True ] && [ "$(feld staende)" = 1 ] && ! grep -q "box.example" "$J/daten/sicherung-extern.php"'
  lauf pruefen
  ok "SFTP: pruefen holt das neueste Archiv zurück, byteweise gleich" '[ $CODE = 0 ] && echo "$AUS" | grep -q "byteweise gleich"'
  lauf passwort-neu
  ok "SFTP: passwort-neu wechselt das Passwort (ein Schlüssel auf der Storage Box), neues einmal gezeigt; status liest danach" '[ $CODE = 0 ] && [ "$(cat "$J/.sicherung-extern-passwort")" != "$PW" ] && [ "$(echo "$AUS" | grep -cF "$(cat "$J/.sicherung-extern-passwort")")" = 1 ] && [ "$(find "$T/box/wochenangebot/keys" -type f | wc -l)" = 1 ]'
  lauf status
  ok "SFTP: status zeigt Ziel und Stände" '[ $CODE = 0 ] && echo "$AUS" | grep -q "sftp:benutzer-sub1@box.example:wochenangebot" && echo "$AUS" | grep -q "Stände: 1"'
  touch "$T/box-weg"
  lauf jetzt
  ok "SFTP: Storage Box nicht erreichbar: Rückgabewert 1, Fehlerstatus ohne Namen der Gegenstelle" '[ $CODE = 1 ] && [ "$(feld ok)" = False ] && feld meldung | grep -q "Übertragung fehlgeschlagen" && ! grep -q "box.example" "$J/daten/sicherung-extern.php"'
  lauf status
  ok "SFTP: status bei nicht erreichbarer Storage Box: Rückgabewert 1" '[ $CODE = 1 ] && echo "$AUS" | grep -q "nicht erreichbar"'
fi
echo "sicherung-extern.sh: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
