#!/bin/sh
# Zentrale Anmeldung – Konten in Keycloak über die Serverkonsole verwalten (ohne Browser und ohne SSH-Tunnel).
# Im Installationsordner auf dem Server ausführen (dort, wo .env liegt), Keycloak muss laufen (Schritt 3).
#
#   sh deploy/anmeldung/konten.sh verwaltung     # einmalig (Schritt 4): dauerhaftes Verwaltungskonto statt Start-Konto
#   sh deploy/anmeldung/konten.sh anlegen <benutzername> <e-mail> <vorname> <nachname>
#   sh deploy/anmeldung/konten.sh startpasswort <benutzername>   # neues Startpasswort (z. B. vergessen)
#   sh deploy/anmeldung/konten.sh zuruecksetzen <benutzername>   # Handy/Passkey verloren: zweiten Faktor neu einrichten
#   sh deploy/anmeldung/konten.sh passkey <benutzername>         # bei der nächsten Anmeldung Passkey einrichten
#   sh deploy/anmeldung/konten.sh sperren <benutzername>         # deaktivieren und überall abmelden
#   sh deploy/anmeldung/konten.sh entsperren <benutzername>
#   sh deploy/anmeldung/konten.sh liste
#   sh deploy/anmeldung/konten.sh mail-einrichten [<test-adresse>]  # Mailversand von Keycloak über das Postfach der Anwendung
#   sh deploy/anmeldung/konten.sh einladen <benutzername> <e-mail> <vorname> <nachname>   # Konto anlegen und einladen
#   sh deploy/anmeldung/konten.sh einladen <benutzername>         # Einladung erneut senden
#
# Einladung: Keycloak schickt eine Mail mit Link (72 Stunden gültig); darüber legt der Mitarbeiter selbst Passwort und
# Einmalcode fest – kein Passwort per Mail. Vorher muss es das Mitarbeiterkonto im Eingabebereich geben.
#
# - Mitarbeiter erhalten ein Startpasswort (einmal angezeigt) und müssen bei der ersten Anmeldung ein eigenes Passwort
#   und den Einmalcode einrichten. Der Benutzername muss dem im Eingabebereich entsprechen (Verwaltung → Nutzer).
# - Rechte vergibt weiter nur die Anwendung; ein Keycloak-Konto allein gibt keinen Zugang.
# - Das Verwaltungskonto (Realm 'master') hat ein langes Zufallspasswort in .env (KC_VERWALTUNG_PASSWORD, nie anzeigen).
set -eu
umask 077
ENV="$(pwd)/.env"
# Werkzeug von Keycloak im Container; die Tests setzen KCADM/KC_SERVER auf eine lokale Installation
KCADM=${KCADM:-docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml exec -T keycloak /opt/keycloak/bin/kcadm.sh}
KC_SERVER=${KC_SERVER:-http://localhost:8080}
REALM=mitarbeiter
VERWALTUNG=verwaltung
# PHP der Anwendung (Postfach und Mitarbeiterkonten lesen) und Ordner des Keycloak-Tresors (Dateien, nur Keycloak liest sie)
APP_PHP=${APP_PHP:-docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml exec -T -u www-data app php}
VAULT_DIR=${KC_VAULT_HOST_DIR:-$(pwd)/daten-anmeldung/vault}
KC_UID=${KC_UID:-1000}
EINLADUNG_STUNDEN=72
FEHLER=$(mktemp); trap 'rm -f "$FEHLER"' EXIT

abbruch() { echo "Abbruch: $*" >&2; exit 1; }
[ -f "$ENV" ] || abbruch "$ENV nicht gefunden – im Installationsordner ausführen."
wert() { sed -n "s/^$1=//p" "$ENV" | tail -1; }
startwert() { v=$(sed -n "s/^$1=//p" "$START" 2>/dev/null | tail -1); [ -n "$v" ] && echo "$v" || wert "$1"; }
zufall() { od -An -N48 -tx1 /dev/urandom | tr -d ' \n' | cut -c1-48; }
# Startpasswort: gut vorlesbar (keine 0/O/1/l/I), 16 Zeichen in Vierergruppen; Realm verlangt mindestens 12
startpasswort() { tr -dc 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789' < /dev/urandom | head -c 16 | sed 's/\(....\)/\1-/g; s/-$//'; }

kc_als() { # kc_als <benutzer> <passwort> <kcadm-Befehl…>
  u=$1; p=$2; shift 2
  # shellcheck disable=SC2086  # KCADM ist bewusst ein Befehl mit Argumenten
  $KCADM "$@" --no-config --server "$KC_SERVER" --realm master --user "$u" --password "$p" 2>"$FEHLER"
}
bereit() { [ -n "$(wert KC_VERWALTUNG_PASSWORD)" ] || abbruch "noch kein Verwaltungskonto – zuerst: sh deploy/anmeldung/konten.sh verwaltung"; }
kc() {
  pw=$(wert KC_VERWALTUNG_PASSWORD)
  kc_als "$VERWALTUNG" "$pw" "$@" || { grep -v '^Logging into' "$FEHLER" >&2; abbruch "Keycloak hat den Befehl abgelehnt (läuft Keycloak? Schritt 3)."; }
}
name_pruefen() { # gleiche Regel wie im Eingabebereich (clean_username); Keycloak speichert ohnehin klein
  printf '%s' "$1" | grep -Eq '^[a-z0-9][a-z0-9._-]{1,31}$' || abbruch "Benutzername: 2–32 Zeichen, nur a–z, Ziffern, Punkt, Binde- und Unterstrich (wie im Eingabebereich)."
}
klein() { printf '%s' "$1" | tr 'A-Z' 'a-z'; }
nutzer_id() { kc get users -r "$REALM" -q username="$1" -q exact=true --fields id --format csv --noquotes | head -1; }
nutzer_id_pflicht() { id=$(nutzer_id "$1"); [ -n "$id" ] || abbruch "Konto '$1' gibt es in Keycloak nicht (Liste: konten.sh liste)."; echo "$id"; }

verwaltung() {
  if [ -z "$(wert KC_VERWALTUNG_PASSWORD)" ]; then
    [ -n "$(tail -c1 "$ENV")" ] && echo >> "$ENV"
    printf 'KC_VERWALTUNG_PASSWORD=%s\n' "$(zufall)" >> "$ENV"; chmod 600 "$ENV"
    echo "erzeugt:   KC_VERWALTUNG_PASSWORD (in .env)"
  fi
  pw=$(wert KC_VERWALTUNG_PASSWORD)
  START="$(pwd)/daten-anmeldung/einrichtung.env"   # Start-Konto (einrichten.sh); ältere Fassungen: in .env
  start=$(startwert KC_BOOTSTRAP_ADMIN_USERNAME); start_pw=$(startwert KC_BOOTSTRAP_ADMIN_PASSWORD)
  if ! kc_als "$VERWALTUNG" "$pw" get realms/master --fields realm >/dev/null; then
    [ -n "$start" ] && [ -n "$start_pw" ] || abbruch "Verwaltungskonto fehlt und kein Start-Konto (daten-anmeldung/einrichtung.env)."
    kc_als "$start" "$start_pw" get realms/master --fields realm >/dev/null \
      || { grep -v '^Logging into' "$FEHLER" >&2; abbruch "Anmeldung mit dem Start-Konto fehlgeschlagen (läuft Keycloak? Schritt 3)."; }
    if [ -z "$(kc_als "$start" "$start_pw" get users -r master -q username="$VERWALTUNG" -q exact=true --fields id --format csv --noquotes)" ]; then
      kc_als "$start" "$start_pw" create users -r master -s username="$VERWALTUNG" -s enabled=true >/dev/null
    fi
    kc_als "$start" "$start_pw" set-password -r master --username "$VERWALTUNG" --new-password "$pw" >/dev/null
    kc_als "$start" "$start_pw" add-roles -r master --uusername "$VERWALTUNG" --rolename admin >/dev/null
    kc_als "$VERWALTUNG" "$pw" get realms/master --fields realm >/dev/null || abbruch "neues Verwaltungskonto funktioniert nicht – Start-Konto bleibt bestehen."
    echo "angelegt:  Verwaltungskonto '$VERWALTUNG' (Realm master)"
  else
    echo "vorhanden: Verwaltungskonto '$VERWALTUNG'"
  fi
  if [ -n "$start" ] && [ "$start" != "$VERWALTUNG" ]; then
    id=$(kc get users -r master -q username="$start" -q exact=true --fields id --format csv --noquotes | head -1)
    if [ -n "$id" ]; then kc delete "users/$id" -r master >/dev/null; echo "gelöscht:  Start-Konto '$start'"; fi
  fi
  if grep -q '^KC_BOOTSTRAP_ADMIN_' "$ENV"; then
    sed -i '/^KC_BOOTSTRAP_ADMIN_/d' "$ENV"; echo "entfernt:  KC_BOOTSTRAP_ADMIN_* aus .env"
  fi
  if [ -f "$START" ]; then rm -f "$START"; echo "entfernt:  daten-anmeldung/einrichtung.env (Start-Konto)"; fi
  echo "Fertig. Nächster Schritt: Mitarbeiterkonten anlegen (konten.sh anlegen …)."
}

anlegen() {
  [ $# -eq 4 ] || abbruch "Aufruf: konten.sh anlegen <benutzername> <e-mail> <vorname> <nachname>"
  name_pruefen "$1"
  printf '%s' "$2" | grep -Eq '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' || abbruch "E-Mail-Adresse ungültig."
  id=$(nutzer_id "$1")
  [ -z "$id" ] || abbruch "Konto '$1' gibt es schon (neues Startpasswort: konten.sh startpasswort $1)."
  kc create users -r "$REALM" -s username="$1" -s email="$2" -s firstName="$3" -s lastName="$4" \
    -s enabled=true -s emailVerified=true -s 'requiredActions=["UPDATE_PASSWORD","CONFIGURE_TOTP"]' >/dev/null
  neues_startpasswort "$1"
}

neues_startpasswort() {
  sp=$(startpasswort)
  kc set-password -r "$REALM" --username "$1" --new-password "$sp" --temporary >/dev/null
  echo "Konto '$1' – Startpasswort (nur jetzt sichtbar, persönlich weitergeben): $sp"
  echo "Bei der ersten Anmeldung: eigenes Passwort festlegen und Einmalcode (App) einrichten."
}

startpasswort_neu() {
  [ $# -eq 1 ] || abbruch "Aufruf: konten.sh startpasswort <benutzername>"
  name_pruefen "$1"; id=$(nutzer_id_pflicht "$1")
  neues_startpasswort "$1"
}

zuruecksetzen() { # nur nach persönlicher Prüfung der Person: Einmalcode und Passkeys löschen, neues Startpasswort
  [ $# -eq 1 ] || abbruch "Aufruf: konten.sh zuruecksetzen <benutzername>"
  name_pruefen "$1"; id=$(nutzer_id_pflicht "$1")
  kc create "users/$id/logout" -r "$REALM" >/dev/null
  liste_cred=$(kc get "users/$id/credentials" -r "$REALM" --fields id,type --format csv --noquotes)
  for z in $liste_cred; do
    case "${z#*,}" in otp|webauthn|webauthn-passwordless) kc delete "users/$id/credentials/${z%%,*}" -r "$REALM" >/dev/null ;; esac
  done
  kc update "users/$id" -r "$REALM" -s 'requiredActions=["UPDATE_PASSWORD","CONFIGURE_TOTP"]' >/dev/null
  echo "Konto '$1': Einmalcode und Passkeys gelöscht, überall abgemeldet."
  neues_startpasswort "$1"
}

passkey() {
  [ $# -eq 1 ] || abbruch "Aufruf: konten.sh passkey <benutzername>"
  name_pruefen "$1"; id=$(nutzer_id_pflicht "$1")
  kc update "users/$id" -r "$REALM" -s 'requiredActions=["webauthn-register"]' >/dev/null
  echo "Konto '$1': bei der nächsten Anmeldung (nach dem Einmalcode) wird ein Passkey eingerichtet."
}

sperren() {
  [ $# -eq 1 ] || abbruch "Aufruf: konten.sh sperren <benutzername>"
  name_pruefen "$1"; id=$(nutzer_id_pflicht "$1")
  kc update "users/$id" -r "$REALM" -s enabled=false >/dev/null
  kc create "users/$id/logout" -r "$REALM" >/dev/null
  echo "Konto '$1' gesperrt und überall abgemeldet."
}

entsperren() {
  [ $# -eq 1 ] || abbruch "Aufruf: konten.sh entsperren <benutzername>"
  name_pruefen "$1"; id=$(nutzer_id_pflicht "$1")
  kc update "users/$id" -r "$REALM" -s enabled=true >/dev/null
  echo "Konto '$1' entsperrt."
}

app() { # app <postfach|nutzer> [name] – Abfrage im App-Container (deploy/anmeldung/app-abfrage.php über die Standardeingabe)
  # shellcheck disable=SC2086  # APP_PHP ist bewusst ein Befehl mit Argumenten
  $APP_PHP -- "$@" < deploy/anmeldung/app-abfrage.php
}

mail_einrichten() {
  [ $# -le 1 ] || abbruch "Aufruf: konten.sh mail-einrichten [<test-adresse>]"
  command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
  mkdir -p "$VAULT_DIR"; chmod 700 "$VAULT_DIR"
  # Postfach der Anwendung lesen; Passwort nur in die Tresor-Datei (Realm „mitarbeiter“, Schlüssel smtp_password),
  # die Keycloak-Datenbank (und damit ihre Sicherung) enthält nur den Verweis ${vault.smtp_password}
  einstellungen=$(app postfach | python3 -c '
import json, os, sys
c = json.load(sys.stdin); pfad = sys.argv[1]
neu = pfad + ".neu"
fd = os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f: f.write(c["pass"])
os.replace(neu, pfad)
sec = c["secure"]
smtp = {"host": c["host"], "port": str(c["port"]), "from": c["from"], "fromDisplayName": c["fromName"],
        "replyTo": c["replyTo"] or "", "ssl": str(sec == "ssl").lower(), "starttls": str(sec == "starttls").lower(),
        "auth": str(bool(c["user"])).lower(), "user": c["user"] or "", "password": "${vault.smtp_password}"}
print(json.dumps({"smtpServer": smtp}))
print("Postfach: %s (%s), Absender %s, Quelle: %s" % (c["host"], sec, c["from"], "Eingabebereich" if c["quelle"] == "admin" else ".env"), file=sys.stderr)
' "$VAULT_DIR/mitarbeiter_smtp__password") || abbruch "Postfach der Anwendung nicht lesbar (läuft die App? E-Mail im Eingabebereich eingerichtet?)."
  if [ "$(id -u)" = 0 ]; then chown -R "$KC_UID" "$VAULT_DIR"; fi
  printf '%s\n' "$einstellungen" | kc update "realms/$REALM" -f - >/dev/null
  # „Zurück zur Anwendung“ nach den Aktionen der Einladung: Startadresse der Clients (im Realm-Import schon gesetzt)
  for paar in dashboard=https://dashboard-stafl.de/ angebot=https://angebot.dashboard-stafl.de/admin/; do
    cid=$(kc get clients -r "$REALM" -q clientId="${paar%%=*}" --fields id --format csv --noquotes | head -1)
    [ -z "$cid" ] || [ -n "${KC_BASEURL_BEHALTEN:-}" ] || kc update "clients/$cid" -r "$REALM" -s baseUrl="${paar#*=}" >/dev/null
  done
  echo "Mailversand der Anmeldung eingerichtet (Passwort nur in der Tresor-Datei, nicht in der Datenbank)."
  if [ $# -eq 1 ]; then
    printf '%s' "$1" | grep -Eq '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' || abbruch "Test-Adresse ungültig."
    vid=$(kc get users -r master -q username="$VERWALTUNG" -q exact=true --fields id --format csv --noquotes | head -1)
    kc update "users/$vid" -r master -s email="$1" >/dev/null   # Testmail geht an die Adresse des Verwaltungskontos
    printf '%s\n' "$einstellungen" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["smtpServer"]))' \
      | kc create "realms/$REALM/testSMTPConnection" -f - >/dev/null
    echo "Testmail an $1 verschickt – bitte Posteingang prüfen."
  fi
}

einladen() {
  [ $# -eq 1 ] || [ $# -eq 4 ] || abbruch "Aufruf: konten.sh einladen <benutzername> [<e-mail> <vorname> <nachname>]"
  name_pruefen "$1"
  stand=$(app nutzer "$1") || abbruch "Mitarbeiterkonten der Anwendung nicht lesbar (läuft die App?)."
  case "$stand" in
    aktiv) ;;
    gesperrt) abbruch "Das Mitarbeiterkonto '$1' ist im Eingabebereich gesperrt – erst entsperren." ;;
    *) abbruch "Im Eingabebereich gibt es kein Mitarbeiterkonto '$1' – zuerst dort anlegen (gleicher Benutzername)." ;;
  esac
  kc get "realms/$REALM" | python3 -c 'import json,sys; sys.exit(0 if (json.load(sys.stdin).get("smtpServer") or {}).get("host") else 1)' \
    || abbruch "Mailversand noch nicht eingerichtet – zuerst: sh deploy/anmeldung/konten.sh mail-einrichten"
  id=$(nutzer_id "$1")
  if [ -z "$id" ]; then
    [ $# -eq 4 ] || abbruch "Konto '$1' gibt es in Keycloak noch nicht – mit E-Mail, Vor- und Nachname aufrufen."
    printf '%s' "$2" | grep -Eq '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' || abbruch "E-Mail-Adresse ungültig."
    kc create users -r "$REALM" -s username="$1" -s email="$2" -s firstName="$3" -s lastName="$4" \
      -s enabled=true -s emailVerified=true -s 'requiredActions=["UPDATE_PASSWORD","CONFIGURE_TOTP"]' >/dev/null
    id=$(nutzer_id "$1"); echo "angelegt:  Konto '$1'"
  elif [ $# -eq 4 ]; then
    abbruch "Konto '$1' gibt es schon – Einladung erneut senden mit: konten.sh einladen $1"
  fi
  # Einmalcode nur einrichten lassen, wenn noch keiner da ist (sonst nur Passwort)
  aktionen='["UPDATE_PASSWORD","CONFIGURE_TOTP"]'
  if kc get "users/$id/credentials" -r "$REALM" --fields type --format csv --noquotes | grep -qx otp; then aktionen='["UPDATE_PASSWORD"]'; fi
  kc update "users/$id/execute-actions-email" -r "$REALM" -q lifespan=$((EINLADUNG_STUNDEN * 3600)) -q client_id=dashboard -b "$aktionen" >/dev/null
  echo "Einladung an '$1' verschickt (Link $EINLADUNG_STUNDEN Stunden gültig): eigenes Passwort und Einmalcode festlegen, danach https://dashboard-stafl.de/"
}

liste() {
  echo "benutzername,vorname,nachname,e-mail,aktiv"
  kc get users -r "$REALM" --fields username,firstName,lastName,email,enabled --format csv --noquotes
}

befehl=${1:-}; [ $# -gt 0 ] && shift
if [ $# -gt 0 ]; then n=$(klein "$1"); shift; set -- "$n" "$@"; fi
case "$befehl" in anlegen|startpasswort|zuruecksetzen|passkey|sperren|entsperren|liste|mail-einrichten|einladen) bereit ;; esac
case "$befehl" in
  verwaltung) verwaltung ;;
  anlegen) anlegen "$@" ;;
  startpasswort) startpasswort_neu "$@" ;;
  zuruecksetzen) zuruecksetzen "$@" ;;
  passkey) passkey "$@" ;;
  sperren) sperren "$@" ;;
  entsperren) entsperren "$@" ;;
  liste) liste ;;
  mail-einrichten) mail_einrichten "$@" ;;
  einladen) einladen "$@" ;;
  *) sed -n '2,/^set -eu/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
