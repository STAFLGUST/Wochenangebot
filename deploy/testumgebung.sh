#!/bin/sh
# Testumgebung test.<Domain> auf demselben Server – vollständig getrennt vom Echtbetrieb
# (eigener Ordner, eigener Container, nur Testdaten, keine E-Mails, Passwortschutz).
#
#   sh deploy/testumgebung.sh einrichten            einmalig: Ordner, Passwortschutz, Testdaten, Start
#   sh deploy/testumgebung.sh einspielen <Zweig>    Stand eines GitHub-Zweigs zeigen, z. B. feature/xyz oder main
#   sh deploy/testumgebung.sh zuruecksetzen         Testdaten neu (danach Ersteinrichtung im Browser)
#   sh deploy/testumgebung.sh passwort              Zugangspasswort der Testumgebung ändern
#   sh deploy/testumgebung.sh status | starten | stoppen
#
# Aufruf aus dem Ordner des Echtbetriebs (/opt/wochenangebot). Verändert dort nichts.
set -eu

PROD=$(cd "$(dirname "$0")/.." && pwd)
ZIEL=${WA_TEST_DIR:-/opt/wochenangebot-test}
REPO_URL=${WA_TEST_REPO:-https://github.com/STAFLGUST/Wochenangebot.git}
PHP_IMAGE=php:8.3-apache@sha256:9f1f03b7e093c8e70227d782e31a305590ab71d7b48c076589dcc92ba8c9300c   # wie docker-compose.yml (tests/deploy/test_images.py)

fehler() { echo "FEHLER: $*" >&2; exit 1; }
dc() { docker compose --project-directory "$ZIEL" -f "$ZIEL/docker-compose.yml" "$@"; }

# Eigenes Netz „wochenangebot-edge“ (legt docker-compose.yml des Echtbetriebs an): Caddy ↔ Testumgebung,
# ohne Zugang zur Produktiv-App. Fehlt es, läuft der Echtbetrieb noch mit einer älteren Version.
edge_pruefen() {
  docker network inspect wochenangebot-edge >/dev/null 2>&1 || fehler "Netz 'wochenangebot-edge' fehlt – bitte zuerst den Echtbetrieb mit der aktuellen Version starten (Release einspielen bzw. 'docker compose up -d' im Ordner $PROD)."
}

vorlagen_kopieren() {
  cp "$PROD/deploy/testumgebung/docker-compose.yml" "$ZIEL/docker-compose.yml"
  cp "$PROD/deploy/testumgebung/apache-schutz.conf" "$ZIEL/apache-schutz.conf"
}

daten_neu() {
  [ -d "$ZIEL/src/tests/fixtures/data-seed" ] || fehler "Testdaten fehlen in $ZIEL/src"
  rm -rf "$ZIEL/daten"
  mkdir -p "$ZIEL/daten"
  cp -R "$ZIEL/src/tests/fixtures/data-seed/." "$ZIEL/daten/"
  chown -R 33:33 "$ZIEL/daten" 2>/dev/null || true   # www-data im Container
}

# Versionsnummern und Prüfliste für den Programmordner des eingespielten Zweigs. Nie Code des Zweigs auf dem Server
# ausführen: Ein Zweig ist nicht freigegeben und liefe hier neben dem Echtbetrieb (.env, Daten, Docker). Deshalb
# bearbeitet das Werkzeug des Echtbetriebs (freigegebener Stand) nur die Dateien unter src/app – als root nur mit den
# Rechten von www-data (uid 33), damit Verweise im Zweig auf Dateien außerhalb nichts überschreiben können.
bereitstellen_test() {
  [ -f "$PROD/deploy/bereitstellen.py" ] && [ -d "$ZIEL/src/app" ] || return 1
  if [ "$(id -u)" != 0 ]; then
    python3 -I "$PROD/deploy/bereitstellen.py" --verzeichnis "$ZIEL/src/app"
    return
  fi
  command -v setpriv >/dev/null || { echo "Hinweis: setpriv fehlt – Bereitstellung übersprungen (läuft nie als root)"; return 1; }
  chown -R -h 33:33 "$ZIEL/src/app"   # -h: nur die Verweise selbst, nie ihr Ziel
  setpriv --reuid=33 --regid=33 --clear-groups python3 -I "$PROD/deploy/bereitstellen.py" --verzeichnis "$ZIEL/src/app"
}

passwort_setzen() {
  printf 'Benutzername für die Testumgebung [test]: '
  read -r NUTZER
  NUTZER=${NUTZER:-test}
  case "$NUTZER" in *[!A-Za-z0-9._-]*) fehler "Benutzername nur aus Buchstaben, Ziffern, . _ -" ;; esac
  stty -echo 2>/dev/null || true
  printf 'Passwort (mind. 10 Zeichen, wird nicht angezeigt): '; read -r PW1; echo
  printf 'Passwort wiederholen: '; read -r PW2; echo
  stty echo 2>/dev/null || true
  [ "$PW1" = "$PW2" ] || fehler "Die Passwörter stimmen nicht überein."
  [ "${#PW1}" -ge 10 ] || fehler "Das Passwort ist zu kurz."
  # Hash im Container erzeugen; das Passwort geht nur über die Standardeingabe, nie in Aufrufparameter
  HASH=$(printf '%s' "$PW1" | docker run --rm -i "$PHP_IMAGE" php -r 'echo password_hash(stream_get_contents(STDIN), PASSWORD_BCRYPT);')
  case "$HASH" in '$2y$'*) ;; *) fehler "Passwort-Hash konnte nicht erzeugt werden." ;; esac
  printf '%s:%s\n' "$NUTZER" "$HASH" > "$ZIEL/zugang.htpasswd"
  chmod 644 "$ZIEL/zugang.htpasswd"
  PW1=''; PW2=''
  echo "Zugang für '$NUTZER' gespeichert."
}

case "${1:-}" in
  einrichten)
    command -v docker >/dev/null || fehler "docker fehlt"
    [ -f "$PROD/.env" ] || fehler "$PROD/.env nicht gefunden – bitte aus dem Ordner des Echtbetriebs aufrufen."
    DOMAIN=$(sed -n 's/^DOMAIN=//p' "$PROD/.env" | tr -d '"'"'"' ' | head -n 1)
    [ -n "$DOMAIN" ] || fehler "DOMAIN fehlt in $PROD/.env"
    CADDY=$(cd "$PROD" && docker compose ps -q caddy)
    [ -n "$CADDY" ] || fehler "Der Caddy-Container des Echtbetriebs läuft nicht."
    edge_pruefen
    mkdir -p "$ZIEL"
    if [ ! -d "$ZIEL/src/.git" ]; then git clone -q "$REPO_URL" "$ZIEL/src"; fi
    vorlagen_kopieren
    printf 'TEST_DOMAIN=test.%s\n' "$DOMAIN" > "$ZIEL/.env"
    [ -f "$ZIEL/zugang.htpasswd" ] || passwort_setzen
    [ -d "$ZIEL/daten" ] || daten_neu
    dc up -d
    echo "Testumgebung läuft: https://test.$DOMAIN (Stand: $(git -C "$ZIEL/src" log -1 --format='%h %s'))"
    echo "Beim ersten Aufruf im Browser: Zugangsdaten der Testumgebung, danach Ersteinrichtung (eigener Test-Administrator)."
    ;;
  einspielen)
    ZWEIG=${2:-}
    case "$ZWEIG" in ''|-*|*..*|*[!A-Za-z0-9._/-]*) fehler "Bitte einen Zweignamen angeben, z. B. feature/xyz oder main." ;; esac
    [ -d "$ZIEL/src/.git" ] || fehler "Testumgebung ist noch nicht eingerichtet (… einrichten)."
    # Nur Zweige des eigenen Repositorys (keine fremden Forks)
    git -C "$ZIEL/src" fetch -q origin "+refs/heads/$ZWEIG:refs/remotes/origin/$ZWEIG" || fehler "Zweig '$ZWEIG' nicht gefunden."
    git -C "$ZIEL/src" checkout -q --detach "origin/$ZWEIG"
    # Versionsnummern und Prüfliste: Werkzeug des Echtbetriebs, nie das des Zweigs (bereitstellen_test)
    bereitstellen_test || echo "Hinweis: Bereitstellung unvollständig (Versionsnummern/Prüfliste)"
    edge_pruefen
    vorlagen_kopieren
    dc up -d --force-recreate   # übernimmt auch geänderte Netz-/Umgebungseinstellungen
    echo "Eingespielt: $ZWEIG – $(git -C "$ZIEL/src" log -1 --format='%h %s')"
    echo "Im Browser einmal neu laden. Testdaten bleiben erhalten (neu: … zuruecksetzen)."
    ;;
  zuruecksetzen)
    printf 'Alle Testdaten löschen und neu anlegen? Zum Bestätigen „ja“ eingeben: '
    read -r OK
    [ "$OK" = "ja" ] || fehler "Abgebrochen."
    dc down
    daten_neu
    dc up -d
    echo "Testdaten neu angelegt. Beim nächsten Aufruf: Ersteinrichtung im Browser."
    ;;
  passwort)
    [ -d "$ZIEL" ] || fehler "Testumgebung ist noch nicht eingerichtet."
    passwort_setzen
    dc restart
    ;;
  status)
    dc ps
    [ -d "$ZIEL/src/.git" ] && echo "Stand: $(git -C "$ZIEL/src" log -1 --format='%h %s (%cr)')"
    ;;
  starten) dc up -d ;;
  stoppen) dc down ;;
  *) sed -n '2,11p' "$0"; exit 1 ;;
esac
