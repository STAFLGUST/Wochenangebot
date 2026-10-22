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
FEHLER=$(mktemp); trap 'rm -f "$FEHLER"' EXIT

abbruch() { echo "Abbruch: $*" >&2; exit 1; }
[ -f "$ENV" ] || abbruch "$ENV nicht gefunden – im Installationsordner ausführen."
wert() { sed -n "s/^$1=//p" "$ENV" | tail -1; }
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
  start=$(wert KC_BOOTSTRAP_ADMIN_USERNAME); start_pw=$(wert KC_BOOTSTRAP_ADMIN_PASSWORD)
  if ! kc_als "$VERWALTUNG" "$pw" get realms/master --fields realm >/dev/null; then
    [ -n "$start" ] && [ -n "$start_pw" ] || abbruch "Verwaltungskonto fehlt und kein Start-Konto in .env (KC_BOOTSTRAP_ADMIN_*)."
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

liste() {
  echo "benutzername,vorname,nachname,e-mail,aktiv"
  kc get users -r "$REALM" --fields username,firstName,lastName,email,enabled --format csv --noquotes
}

befehl=${1:-}; [ $# -gt 0 ] && shift
if [ $# -gt 0 ]; then n=$(klein "$1"); shift; set -- "$n" "$@"; fi
case "$befehl" in anlegen|startpasswort|zuruecksetzen|passkey|sperren|entsperren|liste) bereit ;; esac
case "$befehl" in
  verwaltung) verwaltung ;;
  anlegen) anlegen "$@" ;;
  startpasswort) startpasswort_neu "$@" ;;
  zuruecksetzen) zuruecksetzen "$@" ;;
  passkey) passkey "$@" ;;
  sperren) sperren "$@" ;;
  entsperren) entsperren "$@" ;;
  liste) liste ;;
  *) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
