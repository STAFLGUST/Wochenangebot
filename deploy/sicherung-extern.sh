#!/bin/sh
# Externe Kopie der Datensicherung: der Ordner sicherungen/ (geprüfte Archive von deploy/sichern.sh, Keycloak-Abzüge, Stände der
# Dateiablage) verschlüsselt und inkrementell auf eine Hetzner Storage Box – mit restic über SFTP (Port 23, eigener
# SSH-Schlüssel). Anleitung, Löschschutz und Rücksicherung: docs/plattform/inbetriebnahme-sicherung-extern.md.
# Als root auf dem Server (Hostinger-Browserkonsole):
#
#   sh /opt/wochenangebot/deploy/sicherung-extern.sh einrichten  # Schlüssel und Passwort erzeugen, Repository anlegen, Timer (täglich 03:30)
#   sh /opt/wochenangebot/deploy/sicherung-extern.sh jetzt       # sofort kopieren, danach Aufbewahrung anwenden (ruft auch der Timer auf)
#   sh /opt/wochenangebot/deploy/sicherung-extern.sh status      # Ziel, Timer, letzter Lauf, Zahl und Größe der Stände (ändert nichts)
#   sh /opt/wochenangebot/deploy/sicherung-extern.sh pruefen     # restic check und Rücksicherungsprobe: neuestes Archiv zurückholen, byteweise vergleichen
#   sh /opt/wochenangebot/deploy/sicherung-extern.sh aus         # Timer entfernen; Repository, Schlüssel und Passwort bleiben
#
# Ziel: SICHERUNG_EXTERN_ZIEL=<Benutzer>@<Benutzer>.your-storagebox.de in .env (Unterkonto der Storage Box). Das Passwort der
# Storage Box kennt dieses Skript nie – der Inhaber hinterlegt den öffentlichen Schlüssel selbst (Befehl zeigt „einrichten“).
# Geheimnisse: nur für root lesbare Dateien im Installationsordner, nie in daten/ (dort schreiben die Container) und nie in
# den Sicherungen: .sicherung-extern-schluessel (SSH), .sicherung-extern-passwort (Repository – ohne es ist die externe Kopie
# wertlos, deshalb zusätzlich außerhalb des Servers aufbewahren), .sicherung-extern-hosts (Schlüssel der Gegenstelle, beim
# ersten Kontakt gemerkt), .sicherung-extern-cache/ (Zwischenspeicher von restic).
# Entkoppelt von sichern.sh: wartet, bis dessen Sperre (sicherungen/.sperre) frei ist, hält sie aber nicht – eine lange erste
# Übertragung darf kein Release aufhalten (dessen Sicherung wartet nur 10 Minuten auf die Sperre). Ohne .sperre, *.tmp.
# Aufbewahrung: je Tag ein Stand für 30 Tage, je Woche einer für 8 Wochen, je Monat einer für 12 Monate. Jeder Stand enthält
# den ganzen Ordner, also schon bis zu 30 Tage lokale Sicherungen – so reicht die externe Kopie rund 13 Monate zurück.
# Status: daten/sicherung-extern.php (Karte „Externe Kopie“ unter Sicherheit → System; ohne Ziel und Geheimnisse). Jeder
# Abbruch von „jetzt“ und „pruefen“ hinterlässt dort einen Fehlerstatus. Optional Totmannschalter wie bei sichern.sh:
# HC_SICHERUNG_EXTERN_URL=https://… in .env (bei Fehler wird „/fail“ angehängt).
# Löschschutz: Wer den Server übernimmt, hat Schlüssel und Passwort und kann das Repository löschen. Dagegen helfen nur
# die automatischen Snapshots der Storage Box (bei Hetzner einschalten) – dieses Skript kann das nicht leisten.
set -eu
umask 077
BASIS=$(cd "$(dirname "$0")/.." && pwd)
ENV="$BASIS/.env"
QUELLE="$BASIS/sicherungen"
STATUS="$BASIS/daten/sicherung-extern.php"
SCHLUESSEL="$BASIS/.sicherung-extern-schluessel"
PASSWORT="$BASIS/.sicherung-extern-passwort"
HOSTS="$BASIS/.sicherung-extern-hosts"
ORDNER=wochenangebot      # Ordner des Repositorys auf der Storage Box (relativ: dort ist nur der eigene Startordner beschreibbar)
RECHNER=stafl             # fester Name in den Ständen: die Aufbewahrung gilt auch nach einem Serverwechsel für dieselbe Reihe
TAGE=30; WOCHEN=8; MONATE=12
TIMER=wochenangebot-sicherung-extern
GUARD='<?php http_response_code(404); exit; ?>'
RESTIC=${WA_RESTIC:-restic}
SSH=${WA_SSH:-ssh}
SYSTEMCTL=${WA_SYSTEMCTL:-systemctl}
UNITS=${WA_UNITS:-/etc/systemd/system}
FERTIG=1                  # 0 = Lauf, dessen Abbruch einen Fehlerstatus hinterlässt (jetzt, pruefen)
ARBEIT=""
envwert() { sed -n "s/^$1=//p" "$ENV" 2>/dev/null | tail -1 | tr -d '"'"'"' '; }
ZIEL=$(envwert SICHERUNG_EXTERN_ZIEL)
HC_URL=$(envwert HC_SICHERUNG_EXTERN_URL)
export RESTIC_PASSWORD_FILE="$PASSWORT" RESTIC_CACHE_DIR="$BASIS/.sicherung-extern-cache"
# Das Ziel wird Teil eines Befehls: nur Benutzer@Rechner aus harmlosen Zeichen, nie mit „-“ am Anfang (wäre eine Option für ssh)
ziel_gueltig() { printf '%s' "$ZIEL" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]*@[A-Za-z0-9][A-Za-z0-9.-]*$'; }
SFTP=""
if [ -n "${WA_SICHERUNG_EXTERN_REPO:-}" ]; then   # nur Tests: Repository in einem lokalen Ordner statt auf der Storage Box
  export RESTIC_REPOSITORY="$WA_SICHERUNG_EXTERN_REPO"
else
  export RESTIC_REPOSITORY="sftp:$ZIEL:$ORDNER"
  # shellcheck disable=SC2089  # die Anführungszeichen wertet restic aus (zerlegt sftp.command selbst), nicht die Shell
  SFTP="sftp.command=$SSH -F /dev/null -p 23 -i '$SCHLUESSEL' -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o 'UserKnownHostsFile=$HOSTS' -o ServerAliveInterval=60 -o ServerAliveCountMax=3 $ZIEL -s sftp"
fi
# shellcheck disable=SC2090
r() { "$RESTIC" ${SFTP:+-o "$SFTP"} "$@"; }
echt() { [ -f "$1" ] && [ ! -L "$1" ]; }
eingerichtet() { echt "$SCHLUESSEL" && echt "$PASSWORT" && { [ -z "$SFTP" ] || ziel_gueltig; }; }
abbruch() { echo "Abbruch: $1" >&2; exit 1; }

# Wie status_schreiben() in deploy/sichern.sh: daten/ ist im Container beschreibbar, ein dort angelegter Verweis darf root nie
# umlenken. Die Datei entsteht im Installationsordner und ersetzt den Eintrag nur per Umbenennen (folgt keinem Verweis).
# Jedes Feld wird entschärft und die Meldungen sind eigene, feste Texte: die Datei liegt im Dateibetrieb im Archiv der
# Datensicherung, und sichern.sh verwirft ein Archiv mit einer Datei, die kein gültiges JSON ist.
zahl() { case "$1" in ''|*[!0-9]*) echo 0 ;; *) echo "$1" ;; esac; }
status() { # ok meldung [letzter anzahl groesse]
  ST_TMP=$(mktemp "$BASIS/.status.XXXXXX") || return 0
  printf '%s\n{"t":"%s","ok":%s,"meldung":"%s","letzter":"%s","staende":%s,"groesse":%s}' "$GUARD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$1" "$(printf '%s' "$2" | tr -d '"\\\000-\037')" "$(printf '%s' "${3:-}" | tr -cd '0-9TZ:-')" "$(zahl "${4:-}")" "$(zahl "${5:-}")" > "$ST_TMP" || { rm -f "$ST_TMP"; return 0; }
  chown 33:33 "$ST_TMP" 2>/dev/null || true
  chmod 644 "$ST_TMP"
  mv -fT "$ST_TMP" "$STATUS" || rm -f "$ST_TMP"
}
melden() { # ok|fail
  [ -n "$HC_URL" ] || return 0
  if [ "$1" = ok ]; then curl -fsS -m 10 --retry 3 "$HC_URL" >/dev/null 2>&1 || true
  else curl -fsS -m 10 --retry 3 "$HC_URL/fail" >/dev/null 2>&1 || true; fi
}
aufraeumen() {
  RC=$?
  [ -z "$ARBEIT" ] || rm -rf "$ARBEIT"
  if [ "$FERTIG" -eq 0 ] && [ "$RC" -ne 0 ]; then   # unerwarteter Abbruch: Fehler sichtbar machen
    status false "Abbruch (Code $RC)"
    melden fail
    echo "Externe Kopie abgebrochen (Code $RC)" >&2
  fi
}
trap aufraeumen EXIT
trap 'exit 1' HUP INT TERM   # dash führt den EXIT-Trap bei Signalen sonst nicht aus (systemd TimeoutStartSec, kill)
fehler() { FERTIG=1; status false "$1"; melden fail; echo "Externe Kopie fehlgeschlagen: $1" >&2; exit 1; }
# Ausgabe von restic nur auf die Konsole bzw. ins Journal (kann das Ziel nennen), nie in den Status
zeigen() { tail -5 "$ARBEIT/aus" >&2 || true; }

# „<Anzahl> <Zeit des neuesten Stands in UTC, leer ohne Stand>“ bzw. Größe des Repositorys in Bytes – nur lesend, ohne Sperre im Repository
staende() {
  r snapshots --no-lock --host "$RECHNER" --json | python3 -c 'import datetime, json, re, sys
z = [datetime.datetime.fromisoformat(re.sub(r"\.\d+", "", s["time"]).replace("Z", "+00:00")) for s in json.load(sys.stdin) or []]
print(len(z), max(z).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if z else "")'
}
groesse() { r stats --no-lock --mode raw-data --json | python3 -c 'import json, sys; print(int(json.load(sys.stdin)["total_size"]))'; }
erfolg() { # [warnung]
  S=$(staende) || fehler "Stände im Repository nicht lesbar"
  G=$(groesse) || G=0
  FERTIG=1
  status true "${1:-}" "${S#* }" "${S%% *}" "$G"
  echo "Externe Kopie in Ordnung: ${S%% *} Stände, neuester ${S#* }, $((G / 1048576)) MB im Repository${1:+; Warnung: $1}"
}
# Beginn eines Laufs: nur eingerichtet, nie zwei Läufe gleichzeitig. Die Sperre liegt auf der Passwortdatei, nur lesend
# geöffnet – so entsteht keine weitere Datei und nichts wird beschrieben.
lauf_beginnen() {
  eingerichtet || abbruch "nicht eingerichtet – zuerst: sh deploy/sicherung-extern.sh einrichten"
  exec 8<"$PASSWORT"
  flock -n 8 || abbruch "ein Lauf der externen Kopie läuft bereits"
  FERTIG=0
  ARBEIT=$(mktemp -d "$BASIS/.sicherung-extern-arbeit.XXXXXX")
}

[ "$(id -u)" = 0 ] || [ -n "${WA_OHNE_ROOT:-}" ] || abbruch "als root ausführen."
case "${1:-status}" in
  einrichten)
    [ -f "$ENV" ] || abbruch "$ENV nicht gefunden."
    command -v "$RESTIC" >/dev/null 2>&1 || abbruch "restic fehlt (apt-get install restic)."
    command -v ssh-keygen >/dev/null 2>&1 || abbruch "ssh-keygen fehlt (apt-get install openssh-client)."
    [ -n "${WA_SICHERUNG_EXTERN_REPO:-}" ] || ziel_gueltig || abbruch "Ziel fehlt oder ist ungültig – in $ENV eintragen: SICHERUNG_EXTERN_ZIEL=<Benutzer>@<Benutzer>.your-storagebox.de"
    for F in "$SCHLUESSEL" "$SCHLUESSEL.pub" "$PASSWORT" "$HOSTS"; do
      [ ! -e "$F" ] && [ ! -L "$F" ] || echt "$F" || abbruch "$F ist keine echte Datei (Verweis oder Ordner) – bitte prüfen."
    done
    [ -e "$SCHLUESSEL" ] || ssh-keygen -q -t ed25519 -N '' -C stafl-sicherung-extern -f "$SCHLUESSEL"
    if [ ! -e "$PASSWORT" ]; then
      # ohne leicht verwechselbare Zeichen (0/O, 1/l/I): das Passwort wird auch ausgedruckt und im Ernstfall abgetippt
      NEU=$(mktemp "$BASIS/.sicherung-extern-neu.XXXXXX")
      tr -dc 'A-HJ-NP-Za-km-z2-9' < /dev/urandom | head -c 40 > "$NEU"
      [ "$(wc -c < "$NEU")" -eq 40 ] || { rm -f "$NEU"; abbruch "Passwort konnte nicht erzeugt werden."; }
      mv -T "$NEU" "$PASSWORT"
      echo "================================================================================"
      echo "Passwort des Repositorys (wird nur dieses eine Mal angezeigt):"
      echo
      echo "    $(cat "$PASSWORT")"
      echo
      echo "JETZT außerhalb des Servers aufbewahren: im Passwortmanager UND als Ausdruck."
      echo "Ohne dieses Passwort ist die externe Kopie wertlos – fällt der Server aus, ist es"
      echo "der einzige Weg an die Daten."
      echo "================================================================================"
    fi
    echo "Öffentlicher Schlüssel für die Storage Box:"
    ssh-keygen -y -f "$SCHLUESSEL"
    if [ -n "$SFTP" ]; then
      echo "Hinterlegen (fragt einmal nach dem Passwort des Storage-Box-Zugangs):"
      echo "    cat $SCHLUESSEL.pub | ssh -p 23 -o UserKnownHostsFile=$HOSTS $ZIEL install-ssh-key"
    fi
    ARBEIT=$(mktemp -d "$BASIS/.sicherung-extern-arbeit.XXXXXX")
    ERREICHT=1
    if r cat config >/dev/null 2>&1; then echo "Repository vorhanden."
    elif r init >"$ARBEIT/aus" 2>&1; then echo "Repository angelegt."
    else ERREICHT=0; zeigen; fi
    if [ -s "$HOSTS" ]; then
      echo "Schlüssel der Storage Box, beim ersten Kontakt gemerkt (Fingerabdruck mit den Angaben von Hetzner vergleichen):"
      ssh-keygen -lf "$HOSTS" || true
    fi
    [ "$ERREICHT" = 1 ] || abbruch "Repository nicht erreichbar oder nicht mit diesem Passwort lesbar. Schlüssel hinterlegt (Befehl oben)? Danach erneut: sh deploy/sicherung-extern.sh einrichten"
    cat > "$UNITS/$TIMER.service" <<UNIT
[Unit]
Description=Wochenangebot: externe Kopie der Datensicherung (Storage Box)
After=network-online.target wochenangebot-sicherung.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/sh $BASIS/deploy/sicherung-extern.sh jetzt
Nice=10
IOSchedulingClass=idle
# Notbremse: die erste Übertragung kann Stunden dauern, danach Minuten; das Skript meldet den Abbruch
TimeoutStartSec=12h
UNIT
    cat > "$UNITS/$TIMER.timer" <<'UNIT'
[Unit]
Description=Wochenangebot: externe Kopie der Datensicherung täglich 03:30 Uhr (nach der Sicherung von 02:30)

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=10min
Persistent=true

[Install]
WantedBy=timers.target
UNIT
    $SYSTEMCTL daemon-reload
    $SYSTEMCTL enable --now "$TIMER.timer" >/dev/null 2>&1 || $SYSTEMCTL enable --now "$TIMER.timer"
    echo "Eingerichtet: täglich 03:30 Uhr. Erste Übertragung jetzt starten: sh deploy/sicherung-extern.sh jetzt"
    ;;
  jetzt)
    lauf_beginnen
    [ -d "$QUELLE" ] && [ ! -L "$QUELLE" ] || fehler "Ordner sicherungen/ fehlt oder ist ein Verweis"
    [ ! -e "$QUELLE/.sperre" ] || flock -s -w 600 "$QUELLE/.sperre" true || fehler "Datensicherung läuft noch – externe Kopie ausgelassen"
    [ -n "$(find "$QUELLE" -maxdepth 1 -type f -name 'daten-*.tar.gz' | head -1)" ] || fehler "keine lokale Sicherung vorhanden – nichts zu kopieren"
    r unlock >/dev/null 2>&1 || true   # Sperren abgebrochener Läufe im Repository; fremde, noch gültige bleiben
    RC=0
    r backup --host "$RECHNER" --exclude "$QUELLE/.sperre" --exclude "$QUELLE/.letzter-fehler" --exclude '*.tmp' "$QUELLE" >"$ARBEIT/aus" 2>&1 || RC=$?
    WARNUNG=""
    case $RC in
      0) ;;
      3) zeigen; WARNUNG="einzelne Dateien waren nicht lesbar (z. B. während des Laufs aufgeräumt)" ;;   # Stand ist trotzdem angelegt
      *) zeigen; fehler "Übertragung fehlgeschlagen (restic Code $RC) – Storage Box erreichbar, Schlüssel hinterlegt, Platz frei?" ;;
    esac
    r forget --host "$RECHNER" --keep-daily "$TAGE" --keep-weekly "$WOCHEN" --keep-monthly "$MONATE" --prune >"$ARBEIT/aus" 2>&1 \
      || { zeigen; WARNUNG="kopiert, aber Aufräumen alter Stände fehlgeschlagen${WARNUNG:+; $WARNUNG}"; }
    erfolg "$WARNUNG"
    melden ok
    ;;
  pruefen)
    lauf_beginnen
    r check >"$ARBEIT/aus" 2>&1 || { zeigen; fehler "Prüfung des Repositorys fehlgeschlagen (restic check)"; }
    # Name nur aus Ziffern, „-“ und „_“ (so vergibt ihn sichern.sh): er steht später in Meldung und Status
    DATEI=$(r ls --host "$RECHNER" latest "$QUELLE" 2>/dev/null | grep -F "$QUELLE/daten-" | grep -E '/daten-[0-9_-]+\.tar\.gz$' | sort | tail -1)
    [ -n "$DATEI" ] || fehler "Rücksicherungsprobe: im neuesten Stand liegt kein Archiv daten-*.tar.gz"
    echt "$DATEI" || fehler "Rücksicherungsprobe: lokales Original ${DATEI##*/} fehlt – externe Kopie veraltet?"
    r restore --host "$RECHNER" latest --target "$ARBEIT/zurueck" --include "$DATEI" >"$ARBEIT/aus" 2>&1 || { zeigen; fehler "Rücksicherungsprobe fehlgeschlagen (restic restore)"; }
    cmp -s "$ARBEIT/zurueck$DATEI" "$DATEI" || fehler "Rücksicherungsprobe: ${DATEI##*/} weicht vom lokalen Original ab"
    echo "Geprüft: Repository in Ordnung; ${DATEI##*/} zurückgeholt und byteweise gleich mit dem lokalen Original."
    erfolg
    ;;
  status)
    if ! eingerichtet; then echo "Externe Kopie: nicht eingerichtet (sh deploy/sicherung-extern.sh einrichten)"; exit 0; fi
    echo "Externe Kopie: eingerichtet, Repository $RESTIC_REPOSITORY"
    echo "Timer: $($SYSTEMCTL is-active "$TIMER.timer" 2>/dev/null || true)"
    # nur Anzeige: die Datei liegt in daten/ und ist im Container beschreibbar
    if echt "$STATUS"; then
      sed 1d "$STATUS" | python3 -c 'import json, sys
d = json.load(sys.stdin)
print("Letzter Lauf:", d.get("t"), "– in Ordnung" if d.get("ok") else "– FEHLER", d.get("meldung") or "")' 2>/dev/null || true
    fi
    S=$(staende 2>/dev/null) || abbruch "Repository nicht erreichbar oder noch nicht angelegt."
    echo "Stände: ${S%% *}$([ -z "${S#* }" ] || echo ", neuester ${S#* } (vor $((($(date +%s) - $(date -d "${S#* }" +%s)) / 3600)) Stunden)")"
    echo "Größe des Repositorys: $(($(groesse) / 1048576)) MB"
    ;;
  aus)
    $SYSTEMCTL disable --now "$TIMER.timer" >/dev/null 2>&1 || true
    rm -f "$UNITS/$TIMER.service" "$UNITS/$TIMER.timer"
    $SYSTEMCTL daemon-reload >/dev/null 2>&1 || true
    echo "Externe Kopie aus: Timer entfernt. Repository, Schlüssel und Passwort bleiben; wieder an: sh deploy/sicherung-extern.sh einrichten"
    ;;
  *)
    echo "Aufruf: sh deploy/sicherung-extern.sh einrichten|jetzt|status|pruefen|aus" >&2
    exit 2
    ;;
esac
