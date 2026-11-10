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
#   sh deploy/anmeldung/konten.sh entsperren <benutzername>      # auch nach zu vielen falschen Passwörtern/Codes
#   sh deploy/anmeldung/konten.sh pruefen <benutzername>        # nur lesen: warum klappt die Anmeldung nicht?
#   sh deploy/anmeldung/konten.sh liste
#   sh deploy/anmeldung/konten.sh mail-einrichten [<test-adresse>]  # Mailversand von Keycloak über das Postfach der Anwendung
#   sh deploy/anmeldung/konten.sh design-setzen [standard]     # Anmeldeseite und E-Mails im Plattform-Design (idempotent); „standard“ = Rückfall
#   sh deploy/anmeldung/konten.sh einladen <benutzername> <e-mail> <vorname> <nachname>   # Konto anlegen und einladen
#   sh deploy/anmeldung/konten.sh einladen <benutzername>         # Einladung erneut senden
#   sh deploy/anmeldung/konten.sh realm-aktualisieren             # Realm auf den aktuellen Stand bringen (idempotent)
#   sh deploy/anmeldung/konten.sh passwort-vergessen an|aus|status  # „Passwort vergessen?“ auf der Anmeldeseite (Link per Mail)
#   sh deploy/anmeldung/konten.sh richtlinien                     # Passwortregeln und Kontosperre aus Sicherheit → Einstellungen übernehmen
#   sh deploy/anmeldung/konten.sh verwaist [--loeschen]           # Konten ohne Mitarbeiter (gelöschte Mitarbeiter) anzeigen bzw. löschen
#   sh deploy/anmeldung/konten.sh gruppe-abgleichen [<benutzername>] # welche Konten die Anwendung verwalten darf (nie Administratoren)
#
# Verwaltung aus der Anwendung (Stand 16, ADR-007 Stufe 1b): Der Client „konten“ darf nur Konten in der Gruppe
# „anwendungskonten“ ändern (Passwort, Sperre, Link, Löschen) und neue Konten nur in diese Gruppe legen. In der Gruppe stehen
# die Konten der Mitarbeiter ohne Administratorrolle – Administratoren und Konten mit Verwaltungsrollen von Keycloak nie.
# Wird jemand in der Anwendung Administrator (oder nicht mehr): konten.sh gruppe-abgleichen. Administratoren: startpasswort,
# entsperren, einladen hier in der Konsole.
#
# Passwort vergessen (Inhaber 03.11.2026): auf der Anmeldeseite „Passwort vergessen?“ – Keycloak schickt einen Link an die
# hinterlegte E-Mail-Adresse. Wer einen zweiten Faktor eingerichtet hat, braucht ihn auch dafür (eigener Ablauf
# „mitarbeiter-passwort-vergessen“, ohne „Reset OTP“): Einmalcode und Passkeys bleiben erhalten. Voraussetzung: mail-einrichten.
#
# Einladung: Keycloak schickt eine Mail mit Link (72 Stunden gültig); darüber legt der Mitarbeiter selbst sein Passwort
# fest – kein Passwort per Mail. Den zweiten Faktor verlangt die Anmeldung nur bei Pflicht-Konten (Administratoren u. a.). Vorher muss es das Mitarbeiterkonto im Eingabebereich geben.
#
# - Mitarbeiter erhalten ein Startpasswort (einmal angezeigt) und müssen bei der ersten Anmeldung ein eigenes Passwort
#   festlegen; den zweiten Faktor nur, wenn ihr Konto ihn braucht (Pflicht laut Eingabebereich). Der Benutzername muss dem im Eingabebereich entsprechen (Verwaltung → Nutzer).
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
APP_PHP=${APP_PHP:-docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml exec -T -u www-data app-mitarbeiter php}
VAULT_DIR=${KC_VAULT_HOST_DIR:-$(pwd)/daten-anmeldung/vault}
KC_UID=${KC_UID:-1000}
EINLADUNG_STUNDEN=72
# Realm-Datei aus dem Repository (Clients für neue Hosts; die Tests setzen die Testfassung)
REALM_DATEI=${KC_REALM_DATEI:-$(pwd)/deploy/anmeldung/realm-mitarbeiter.json}
FEHLER=$(mktemp); trap 'rm -f "$FEHLER" "$FEHLER.client"' EXIT

abbruch() { echo "Abbruch: $*" >&2; exit 1; }
[ -f "$ENV" ] || abbruch "$ENV nicht gefunden – im Installationsordner ausführen."
wert() { sed -n "s/^$1=//p" "$ENV" | tail -1; }
startwert() { v=$(sed -n "s/^$1=//p" "$START" 2>/dev/null | tail -1); [ -n "$v" ] && echo "$v" || wert "$1"; }
zufall() { od -An -N48 -tx1 /dev/urandom | tr -d ' \n' | cut -c1-48; }
# Startpasswort: gut vorlesbar (keine 0/O/1/l/I), mindestens 16 Zeichen in Vierergruppen, immer mit Groß- und Kleinbuchstabe
# und Ziffer (Passwortregeln des Realms: Mindestlänge und ggf. gemischte Zeichen, konten.sh richtlinien)
startpasswort() { # startpasswort [<Anzahl Zeichen ohne Striche>]
  while :; do
    s=$(tr -dc 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789' < /dev/urandom | head -c "${1:-16}")
    case "$s" in *[ABCDEFGHJKMNPQRSTUVWXYZ]*) ;; *) continue ;; esac
    case "$s" in *[abcdefghjkmnpqrstuvwxyz]*) ;; *) continue ;; esac
    case "$s" in *[23456789]*) break ;; esac
  done
  printf '%s' "$s" | sed 's/\(....\)/\1-/g; s/-$//'
}

kc_als() { # kc_als <benutzer> <passwort> <kcadm-Befehl…>
  u=$1; p=$2; shift 2
  # Standardeingabe nur bei „-f -“ (Daten über die Eingabe) weiterreichen: docker compose exec liest sie sonst mit und
  # „schluckt“ in Schleifen („… | while read“) die restlichen Zeilen – dann wurde nur der erste Eintrag bearbeitet
  # (im Betrieb: Anmeldemethode nur für das Passwort, nicht für Einmalcode und Passkey → doppelte Code-Abfrage)
  case " $* " in
    *" -f - "*)
      # shellcheck disable=SC2086  # KCADM ist bewusst ein Befehl mit Argumenten
      $KCADM "$@" --no-config --server "$KC_SERVER" --realm master --user "$u" --password "$p" 2>"$FEHLER" ;;
    *)
      # shellcheck disable=SC2086
      $KCADM "$@" --no-config --server "$KC_SERVER" --realm master --user "$u" --password "$p" 2>"$FEHLER" </dev/null ;;
  esac
}
bereit() { [ -n "${KC_ADMIN_PASSWORD_TEST:-}$(wert KC_VERWALTUNG_PASSWORD)" ] || abbruch "noch kein Verwaltungskonto – zuerst: sh deploy/anmeldung/konten.sh verwaltung"; }
kc() {
  pw=${KC_ADMIN_PASSWORD_TEST:-$(wert KC_VERWALTUNG_PASSWORD)}
  kc_als "${KC_ADMIN_USER_TEST:-$VERWALTUNG}" "$pw" "$@" || { grep -v '^Logging into' "$FEHLER" >&2; abbruch "Keycloak hat den Befehl abgelehnt (läuft Keycloak? Schritt 3)."; }
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
  realm_aktualisieren
  echo "Fertig. Nächster Schritt: Mitarbeiterkonten anlegen (konten.sh anlegen …)."
}

anlegen() {
  [ $# -eq 4 ] || abbruch "Aufruf: konten.sh anlegen <benutzername> <e-mail> <vorname> <nachname>"
  name_pruefen "$1"
  printf '%s' "$2" | grep -Eq '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' || abbruch "E-Mail-Adresse ungültig."
  id=$(nutzer_id "$1")
  [ -z "$id" ] || abbruch "Konto '$1' gibt es schon (neues Startpasswort: konten.sh startpasswort $1)."
  kc create users -r "$REALM" -s username="$1" -s email="$2" -s firstName="$3" -s lastName="$4" \
    -s enabled=true -s emailVerified=true -s 'requiredActions=["UPDATE_PASSWORD"]' >/dev/null
  konto_freigeben "$1"
  neues_startpasswort "$1"
}

konto_freigeben() { # nach dem Anlegen in der Konsole: in die Gruppe anwendungskonten, wenn kein Administrator (Stand 16)
  rc=0; gruppe_abgleichen "$1" || rc=$?
  if [ "$rc" = 2 ]; then echo "Hinweis:   Mitarbeiterkonten der Anwendung nicht lesbar – später: sh deploy/anmeldung/konten.sh gruppe-abgleichen $1"; fi
  return 0
}

neues_startpasswort() {
  # so lang, wie die Passwortregel des Realms verlangt (Mindestlänge aus den Einstellungen, konten.sh richtlinien)
  min=$(kc get "realms/$REALM" --fields passwordPolicy | python3 -c '
import json, re, sys
m = re.search(r"length\((\d+)\)", json.load(sys.stdin).get("passwordPolicy") or "")
print(max(16, -(-int(m.group(1)) // 4) * 4) if m else 16)' 2>/dev/null) || min=16
  sp=$(startpasswort "$min")
  kc set-password -r "$REALM" --username "$1" --new-password "$sp" --temporary >/dev/null
  echo "Konto '$1' – Startpasswort (nur jetzt sichtbar, persönlich weitergeben): $sp"
  echo "Bei der ersten Anmeldung: eigenes Passwort festlegen (Einmalcode nur bei Pflicht-Konten)."
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
  kc update "users/$id" -r "$REALM" -s 'requiredActions=["UPDATE_PASSWORD"]' >/dev/null
  echo "Konto '$1': Einmalcode und Passkeys gelöscht, überall abgemeldet."
  neues_startpasswort "$1"
}

passkey() {
  [ $# -eq 1 ] || abbruch "Aufruf: konten.sh passkey <benutzername>"
  name_pruefen "$1"; id=$(nutzer_id_pflicht "$1")
  kc update "users/$id" -r "$REALM" -s 'requiredActions=["webauthn-register"]' >/dev/null
  echo "Konto '$1': bei der nächsten Anmeldung wird ein Passkey eingerichtet."
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
  # auch die automatische Sperre nach Fehlversuchen (Schutz vor Passwort-/Code-Raten, bis 15 Minuten) aufheben
  kc delete "attack-detection/brute-force/users/$id" -r "$REALM" >/dev/null
  echo "Konto '$1' entsperrt (auch die automatische Sperre nach Fehlversuchen aufgehoben)."
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
print("Postfach: %s (%s), Absender %s, Quelle: %s" % (c["host"], sec, c["from"], {"admin": "Eingabebereich", "intern": "Eingabebereich, Postfach für interne E-Mails"}.get(c["quelle"], ".env")), file=sys.stderr)
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
      -s enabled=true -s emailVerified=true -s 'requiredActions=["UPDATE_PASSWORD"]' >/dev/null
    id=$(nutzer_id "$1"); echo "angelegt:  Konto '$1'"
    konto_freigeben "$1"
  elif [ $# -eq 4 ]; then
    abbruch "Konto '$1' gibt es schon – Einladung erneut senden mit: konten.sh einladen $1"
  else
    kc update "users/$id" -r "$REALM" -s 'requiredActions=["UPDATE_PASSWORD"]' >/dev/null   # ältere Einladungen verlangten den Einmalcode
  fi
  # Nur das Passwort; den zweiten Faktor verlangt die Anmeldung selbst, wenn das Konto ihn braucht (Pflicht-Konten)
  aktionen='["UPDATE_PASSWORD"]'
  kc update "users/$id/execute-actions-email" -r "$REALM" -q lifespan=$((EINLADUNG_STUNDEN * 3600)) -q client_id=dashboard -b "$aktionen" >/dev/null
  echo "Einladung an '$1' verschickt (Link $EINLADUNG_STUNDEN Stunden gültig): eigenes Passwort festlegen, danach https://dashboard-stafl.de/"
}

# ── Anmeldeseite und E-Mails im Plattform-Design (Theme „stafl“ aus deploy/anmeldung/theme, per Volume in Keycloak) ──
# Eigener Schritt neben realm-aktualisieren: ändert nur loginTheme und emailTheme des Realms – keine Abläufe, Richtlinien
# oder Clients. Idempotent; „standard“ stellt die mitgelieferten Designs von Keycloak wieder ein (Rückfall).
DESIGN=stafl
STANDARD_DESIGN=keycloak.v2
STANDARD_MAIL=keycloak
name_design() { case "$1" in ""|"$STANDARD_DESIGN"|"$STANDARD_MAIL") echo "Keycloak-Standard" ;; *) echo "$1" ;; esac; }
design_setzen() {
  [ $# -le 1 ] || abbruch "Aufruf: konten.sh design-setzen [standard]"
  # „standard“ setzt die mitgelieferten Designs ausdrücklich: ein leerer Wert ändert loginTheme/emailTheme in Keycloak nicht
  case "${1:-$DESIGN}" in "$DESIGN") soll=$DESIGN; soll_mail=$DESIGN ;; standard) soll=$STANDARD_DESIGN; soll_mail=$STANDARD_MAIL ;; *) abbruch "Aufruf: konten.sh design-setzen [standard]" ;; esac
  bereit
  command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
  # Ausgaben erst ganz lesen (docker compose exec, siehe realm_aktualisieren)
  realm=$(kc get "realms/$REALM" --fields loginTheme,emailTheme)
  ist=$(printf '%s' "$realm" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("loginTheme") or "")')
  ist_mail=$(printf '%s' "$realm" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("emailTheme") or "")')
  [ -n "$ist" ] || ist=$STANDARD_DESIGN
  [ -n "$ist_mail" ] || ist_mail=$STANDARD_MAIL
  if [ "$soll" = "$DESIGN" ]; then
    info=$(kc get serverinfo)
    for art in login email; do
      printf '%s' "$info" | python3 -c 'import json,sys; sys.exit(0 if any(t.get("name") == sys.argv[1] for t in json.load(sys.stdin).get("themes", {}).get(sys.argv[2], [])) else 1)' "$DESIGN" "$art" \
        || abbruch "Keycloak kennt das Design '$DESIGN' ($art) nicht – zuerst Keycloak mit der aktuellen Compose-Datei neu erstellen: docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml up -d keycloak"
    done
  fi
  if [ "$ist" = "$soll" ]; then
    echo "unverändert: Anmeldeseite im Design '$(name_design "$soll")'"
  else
    kc update "realms/$REALM" -s "loginTheme=$soll" >/dev/null
    echo "gesetzt:   Anmeldeseite im Design '$(name_design "$soll")' (vorher '$(name_design "$ist")')"
  fi
  if [ "$ist_mail" = "$soll_mail" ]; then
    echo "unverändert: E-Mails im Design '$(name_design "$soll_mail")'"
  else
    kc update "realms/$REALM" -s "emailTheme=$soll_mail" >/dev/null
    echo "gesetzt:   E-Mails im Design '$(name_design "$soll_mail")' (vorher '$(name_design "$ist_mail")')"
  fi
}

# ── Realm-Stand (Änderungen am laufenden Realm; der Import beim ersten Start gilt nur einmal) ──
# Stand 2: zweiter Faktor nur noch für Pflicht-Konten (entscheidet die Anwendung, twofa_required) und für alle, die ihn
# eingerichtet haben; Anmeldestärke im Claim amr (pwd/otp/hwk); Leerlauf 4 Stunden.
ausfuehrungen() { kc get "authentication/flows/mitarbeiter-browser/executions" -r "$REALM"; }
ausf_id() { # ausf_id <python-Bedingung über e> – ID der ersten passenden Ausführung
  ausfuehrungen | python3 -c "import json,sys; e=[e for e in json.load(sys.stdin) if $1]; print(e[0]['id'] if e else '')"
}
unterfluss() { # unterfluss <eltern-alias> <alias> <beschreibung> – CONDITIONAL-Unterablauf anlegen (falls fehlt)
  if [ -z "$(ausf_id "e.get('displayName')=='$2' and e.get('authenticationFlow')")" ]; then
    kc create "authentication/flows/$1/executions/flow" -r "$REALM" -b "{\"alias\":\"$2\",\"type\":\"basic-flow\",\"provider\":\"registration-page-form\",\"description\":\"$3\"}" >/dev/null
    id=$(ausf_id "e.get('displayName')=='$2' and e.get('authenticationFlow')")
    kc update "authentication/flows/$1/executions" -r "$REALM" -b "{\"id\":\"$id\",\"requirement\":\"CONDITIONAL\"}" >/dev/null
    echo "angelegt:  Ablauf $2"
  fi
}
schritt() { # schritt <ablauf-alias> <provider> [<config-json>] – REQUIRED-Ausführung anhängen
  kc create "authentication/flows/$1/executions/execution" -r "$REALM" -b "{\"provider\":\"$2\"}" >/dev/null
  id=$(kc get "authentication/flows/$1/executions" -r "$REALM" | python3 -c "import json,sys; print([e['id'] for e in json.load(sys.stdin) if e.get('providerId')=='$2'][-1])")
  kc update "authentication/flows/$1/executions" -r "$REALM" -b "{\"id\":\"$id\",\"requirement\":\"REQUIRED\"}" >/dev/null
  if [ -n "${3:-}" ]; then kc create "authentication/executions/$id/config" -r "$REALM" -b "$3" >/dev/null; fi
}

prioritaet() { # prioritaet <ablauf> <provider oder unterablauf> <zahl> – nur direkte Ausführungen des Ablaufs, nur wenn abweichend
  kc get "authentication/flows/$1/executions" -r "$REALM" | python3 -c "
import json, sys
es = json.load(sys.stdin); top = min(e['level'] for e in es)
for e in es:
    if e['level'] == top and '$2' in (e.get('providerId'), e.get('displayName')) and e.get('priority') != $3:
        print(json.dumps({'id': e['id'], 'requirement': e['requirement'], 'priority': $3}))" | while read -r j; do
    kc update "authentication/flows/$1/executions" -r "$REALM" -b "$j" >/dev/null
  done
}

# Client eines neuen Hosts anlegen (Stand 3: verwaltung, Stand 4: bestand, Stand 5: hr, Stand 6: crm, Stand 7: marketing, Stand 9: sicherheit, Stand 10: controlling, Stand 11: leergut, Stand 12: rewe, Stand 13: qs). Definition aus der Realm-Datei, Geheimnisse aus .env – fehlen sie,
# werden sie wie von einrichten.sh erzeugt (nie angezeigt). Danach liest die Anwendung sie erst nach einem Neustart.
# Stand 8: Client „konten“ (nur Service-Account, kein Host): die Verwaltung der Anwendung steuert damit die Mitarbeiterkonten
# (Passwort setzen, entsperren, Link, anlegen – lib/anmeldekonten.php); Geheimnis OIDC_SECRET_KONTEN, kein Sitzungsschlüssel.
ENV_NEU=0
client_anlegen() { # client_anlegen <clientId>
  c=$1; n=$(printf '%s' "$1" | tr 'a-z' 'A-Z')
  [ -n "$(kc get clients -r "$REALM" -q clientId="$c" --fields id --format csv --noquotes | head -1)" ] && return 0
  [ -f "$REALM_DATEI" ] || abbruch "$REALM_DATEI fehlt – Stand von main einspielen."
  gs="SECRET CRYPTO"; [ "$c" = konten ] && gs=SECRET   # Service-Account ohne Anmeldeseite: kein Sitzungsschlüssel
  for g in $gs; do
    if [ -z "$(wert "OIDC_${g}_$n")" ]; then
      [ -n "$(tail -c1 "$ENV")" ] && echo >> "$ENV"
      printf 'OIDC_%s_%s=%s\n' "$g" "$n" "$(zufall)" >> "$ENV"; ENV_NEU=1
      echo "erzeugt:   OIDC_${g}_$n in .env"
    fi
  done
  # Geheimnis über die Umgebung an python und über die Standardeingabe an Keycloak – nie als Argument (Prozessliste)
  GEHEIM=$(wert "OIDC_SECRET_$n") python3 -c '
import json, os, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
c = [x for x in r.get("clients", []) if x.get("clientId") == sys.argv[2]]
if not c: sys.exit("Client " + sys.argv[2] + " fehlt in " + sys.argv[1])
t = json.dumps(c[0]).replace("@GEHEIM_" + sys.argv[2].upper() + "@", os.environ["GEHEIM"])
if "@GEHEIM_" in t: sys.exit("Platzhalter nicht ersetzt")
print(t)' "$REALM_DATEI" "$c" > "$FEHLER.client" || { rm -f "$FEHLER.client"; abbruch "Client $c: Definition nicht lesbar."; }
  kc create clients -r "$REALM" -f - < "$FEHLER.client" >/dev/null; rm -f "$FEHLER.client"
  echo "angelegt:  Client $c (Host aus $(basename "$REALM_DATEI"))"
}

# Stand 8: Rechte des Service-Accounts „konten“ – genau view-users und manage-users von realm-management, sonst nichts
# (keine Realm-, Client- oder Rollenverwaltung, kein Anmelden als andere Person). Überzählige Rollen werden entfernt.
# ── Stand 16 (ADR-007 Stufe 1b): Client „konten“ nur für die Gruppe „anwendungskonten“ – nie Administratoren ──
# Feingranulare Verwaltungsrechte von Keycloak (Version 2): eine Regel (Client konten) und eine Berechtigung auf die Gruppe
# mit view-members, manage-members und manage-membership – damit ändert der Client Mitglieder und legt neue Konten nur in
# dieser Gruppe an. In die Gruppe aufnehmen oder daraus entfernen kann er niemanden (manage-group-membership fehlt). Lesen darf
# er weiter alle Konten (view-users), damit die Verwaltung Administratorkonten als solche erkennt.
KONTEN_GRUPPE=anwendungskonten
KONTEN_REGEL="Dienstkonto der Anwendung (Client konten)"
KONTEN_BERECHTIGUNG="Anwendung verwaltet Mitarbeiterkonten (Gruppe anwendungskonten)"
json_id() { # json_id <name>: Kennung des Eintrags mit genau diesem Namen aus einer JSON-Liste (Standardeingabe)
  python3 -c 'import json, sys; print(next((x["id"] for x in json.load(sys.stdin) if x.get("name") == sys.argv[1]), ""))' "$1"
}
gruppe_id() { kc get groups -r "$REALM" -q search="$KONTEN_GRUPPE" -q exact=true --fields id,name | json_id "$KONTEN_GRUPPE"; }

konten_feinrechte() { # konten_feinrechte <Client-ID von konten>
  # Beschreibung des Clients wie in der Realm-Datei (ältere Installationen nannten noch manage-users)
  if [ -f "$REALM_DATEI" ]; then
    besch=$(python3 -c 'import json, sys; print(next((c.get("description", "") for c in json.load(open(sys.argv[1], encoding="utf-8"))["clients"] if c["clientId"] == "konten"), ""))' "$REALM_DATEI" 2>/dev/null) || besch=
    [ -z "$besch" ] || kc update "clients/$1" -r "$REALM" -s "description=$besch" >/dev/null
  fi
  kc update "realms/$REALM" -s adminPermissionsEnabled=true >/dev/null
  gid=$(gruppe_id)
  if [ -z "$gid" ]; then
    kc create groups -r "$REALM" -s name="$KONTEN_GRUPPE" >/dev/null
    gid=$(gruppe_id); [ -n "$gid" ] || abbruch "Gruppe $KONTEN_GRUPPE nicht angelegt."
    echo "angelegt:  Gruppe $KONTEN_GRUPPE (Konten, die die Anwendung verwalten darf – nie Administratoren)"
  fi
  ap=$(kc get clients -r "$REALM" -q clientId=admin-permissions --fields id --format csv --noquotes | head -1)
  [ -n "$ap" ] || abbruch "Feingranulare Verwaltungsrechte nicht verfügbar (Keycloak 26.2 oder neuer nötig)."
  rs="clients/$ap/authz/resource-server"
  pid=$(kc get "$rs/policy" -r "$REALM" -q name="$KONTEN_REGEL" --fields id,name | json_id "$KONTEN_REGEL")
  regel="\"name\":\"$KONTEN_REGEL\",\"description\":\"Nur der Service-Account des Clients konten (Verwaltung der Anwendung)\",\"type\":\"client\",\"logic\":\"POSITIVE\",\"decisionStrategy\":\"UNANIMOUS\",\"clients\":[\"$1\"]"
  if [ -z "$pid" ]; then
    printf '{%s}' "$regel" | kc create "$rs/policy/client" -r "$REALM" -f - >/dev/null
    pid=$(kc get "$rs/policy" -r "$REALM" -q name="$KONTEN_REGEL" --fields id,name | json_id "$KONTEN_REGEL")
    [ -n "$pid" ] || abbruch "Regel '$KONTEN_REGEL' nicht angelegt."
    echo "angelegt:  Regel '$KONTEN_REGEL'"
  else
    printf '{"id":"%s",%s}' "$pid" "$regel" | kc update "$rs/policy/client/$pid" -r "$REALM" -f - >/dev/null
  fi
  bid=$(kc get "$rs/permission" -r "$REALM" -q name="$KONTEN_BERECHTIGUNG" --fields id,name | json_id "$KONTEN_BERECHTIGUNG")
  recht="\"name\":\"$KONTEN_BERECHTIGUNG\",\"description\":\"Passwort, Sperre, Link, Anlegen und Löschen nur für Mitglieder; Administratoren nie in der Gruppe (konten.sh gruppe-abgleichen)\",\"type\":\"scope\",\"logic\":\"POSITIVE\",\"decisionStrategy\":\"UNANIMOUS\",\"resourceType\":\"Groups\",\"resources\":[\"$gid\"],\"scopes\":[\"view-members\",\"manage-members\",\"manage-membership\"],\"policies\":[\"$pid\"]"
  if [ -z "$bid" ]; then
    printf '{%s}' "$recht" | kc create "$rs/permission/scope" -r "$REALM" -f - >/dev/null
    echo "angelegt:  Berechtigung '$KONTEN_BERECHTIGUNG'"
  else
    printf '{"id":"%s",%s}' "$bid" "$recht" | kc update "$rs/permission/scope/$bid" -r "$REALM" -f - >/dev/null
  fi
}

rm_client() { kc get clients -r "$REALM" -q clientId=realm-management --fields id --format csv --noquotes | head -1; }
privilegierte() { # Kennungen der Konten mit direkt zugewiesenen Verwaltungsrollen von Keycloak (realm-management), je Zeile eine
  rm_id=$(rm_client)
  for r in $(kc get "clients/$rm_id/roles" -r "$REALM" --fields name --format csv --noquotes); do
    kc get "clients/$rm_id/roles/$r/users" -r "$REALM" --fields id --format csv --noquotes
  done | sort -u
}
privilegiert() { # privilegiert <Kennung>: hat das Konto Verwaltungsrollen von Keycloak – auch über Gruppen oder zusammengesetzte Rollen?
  [ -n "${rm_id:-}" ] || rm_id=$(rm_client)
  [ "$(kc get "users/$1/role-mappings/clients/$rm_id/composite" -r "$REALM" --fields id | python3 -c 'import json, sys; print(len(json.load(sys.stdin)))')" != 0 ]
}

# Gruppe abgleichen: Mitglieder = Konten von Mitarbeitern der Anwendung ohne Administratorrolle (verknüpft oder gleicher
# Benutzername wie bei der ersten Anmeldung), nie Service-Accounts oder Konten mit Verwaltungsrollen von Keycloak. Rückgabe
# 2 = Anwendung nicht lesbar, 3 = Gruppe fehlt (Realm vor Stand 16) – dann wird nichts geändert.
gruppe_abgleichen() { # gruppe_abgleichen [<benutzername>]
  nur=$(klein "${1:-}")
  gid=$(gruppe_id); [ -n "$gid" ] || return 3
  app_konten=$(app konten 2>/dev/null) || return 2
  printf '%s' "$app_konten" | python3 -c 'import json, sys; d = json.load(sys.stdin); sys.exit(0 if all("admin" in k for k in d["konten"]) else 1)' 2>/dev/null || return 2
  rm_id=
  if [ -n "$nur" ]; then   # ein Konto (nach anlegen/einladen): wenige Aufrufe, Verwaltungsrollen auch über Gruppen geprüft
    nid=$(nutzer_id "$nur"); [ -n "$nid" ] || return 0
    alle="[{\"id\": \"$nid\", \"username\": \"$nur\"}]"
    if privilegiert "$nid"; then priv=$nid; else priv=; fi
  else
    alle=$(kc get users -r "$REALM" --offset 0 --limit 5000 --fields id,username)
    priv=$(privilegierte | tr '\n' ' ')
  fi
  mitglieder=$(kc get "groups/$gid/members" -r "$REALM" --offset 0 --limit 5000 --fields id)
  plan=$(APP_KONTEN="$app_konten" ALLE="$alle" MITGLIEDER="$mitglieder" PRIV="$priv" NUR="$nur" python3 -c '
import json, os
a = json.loads(os.environ["APP_KONTEN"])
mit = {m["id"] for m in json.loads(os.environ["MITGLIEDER"])}
priv = set(os.environ["PRIV"].split())
weg = set(a.get("geloescht", []))
nach_sub = {k["sub"]: k for k in a["konten"] if k.get("sub")}
nach_name = {k["name"]: k for k in a["konten"] if not k.get("sub")}
for u in json.loads(os.environ["ALLE"]):
    n, i = u.get("username", ""), u["id"]
    if os.environ["NUR"] and n != os.environ["NUR"]: continue
    if n.startswith("service-account-"): continue
    k = nach_sub.get(i) or (nach_name.get(n) if i not in weg else None)
    darf = bool(k) and not k.get("admin") and i not in priv
    if darf and i not in mit: print("+", i, n, "-")
    elif not darf and i in mit: print("-", i, n, "Administrator" if (k and k.get("admin")) or i in priv else "ohne Mitarbeiterkonto")')
  if [ -n "$plan" ]; then
    printf '%s\n' "$plan" | while read -r art id n grund; do
      if [ "$art" = + ] && [ -z "$nur" ] && privilegiert "$id"; then   # Verwaltungsrolle über Gruppe oder zusammengesetzte Rolle
        echo "nicht aufgenommen: Konto '$n' (Verwaltungsrollen von Keycloak – nur über die Serverkonsole)"
      elif [ "$art" = + ]; then
        kc update "users/$id/groups/$gid" -r "$REALM" -s realm="$REALM" -s userId="$id" -s groupId="$gid" -n >/dev/null
        echo "aufgenommen: Konto '$n' – die Verwaltung der Anwendung darf es ändern"
      else
        kc delete "users/$id/groups/$gid" -r "$REALM" >/dev/null
        echo "entfernt:  Konto '$n' aus der Gruppe $KONTEN_GRUPPE ($grund – nur noch über die Serverkonsole)"
      fi
    done
  fi
  n=$(kc get "groups/$gid/members" -r "$REALM" --offset 0 --limit 5000 --fields id | python3 -c 'import json, sys; print(len(json.load(sys.stdin)))')
  [ -n "$nur" ] || echo "Gruppe $KONTEN_GRUPPE: $n Konten verwaltet die Anwendung; Administratoren nur über die Serverkonsole."
}

gruppe_abgleichen_befehl() {
  [ $# -le 1 ] || abbruch "Aufruf: konten.sh gruppe-abgleichen [<benutzername>]"
  [ $# -eq 0 ] || name_pruefen "$1"
  command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
  rc=0; gruppe_abgleichen "$@" || rc=$?
  case $rc in
    0) ;;
    2) abbruch "Mitarbeiterkonten der Anwendung nicht lesbar (läuft die App?)." ;;
    3) abbruch "Gruppe $KONTEN_GRUPPE fehlt – zuerst: sh deploy/anmeldung/konten.sh realm-aktualisieren" ;;
    *) exit "$rc" ;;
  esac
}

konten_rechte() {
  cid=$(kc get clients -r "$REALM" -q clientId=konten --fields id --format csv --noquotes | head -1)
  [ -n "$cid" ] || return 0
  sa=$(kc get "clients/$cid/service-account-user" -r "$REALM" --fields id --format csv --noquotes | head -1)
  [ -n "$sa" ] || abbruch "Client konten ohne Service-Account – Realm-Datei prüfen."
  # Stand 17 (Keycloak ab 26.8.2, CVE-2026-19688): die Verwaltungsschnittstelle nimmt nur noch Tokens mit dem Scope
  # kc-admin-api an (sonst 401). Keycloak gibt ihn nur admin-cli und der Admin-Konsole – dem Client konten hier dazu.
  # Ältere Keycloak-Fassungen kennen den Scope nicht: dann nichts zu tun.
  sid=$(kc get client-scopes -r "$REALM" --fields id,name --format csv --noquotes | grep ',kc-admin-api$' | cut -d, -f1 | head -1)
  if [ -n "$sid" ]; then
    case " $(kc get "clients/$cid/default-client-scopes" -r "$REALM" --fields name --format csv --noquotes | tr '\n' ' ') " in
      *" kc-admin-api "*) ;;
      *) kc update "clients/$cid/default-client-scopes/$sid" -r "$REALM" >/dev/null
         echo "gesetzt:   Scope kc-admin-api für den Client konten (Verwaltungsschnittstelle ab Keycloak 26.8.2)" ;;
    esac
  fi
  # Erst die Gruppe mit ihren Rechten, dann abgleichen, zuletzt manage-users entfernen – keine Lücke für die Verwaltung
  konten_feinrechte "$cid"
  rc=0; gruppe_abgleichen || rc=$?
  if [ "$rc" != 0 ]; then
    echo "Hinweis:   Mitarbeiterkonten der Anwendung nicht lesbar – Gruppe $KONTEN_GRUPPE nicht abgeglichen. Bitte danach: sh deploy/anmeldung/konten.sh gruppe-abgleichen"
  fi
  rm_id=$(kc get clients -r "$REALM" -q clientId=realm-management --fields id --format csv --noquotes | head -1)
  ist=$(kc get "users/$sa/role-mappings/clients/$rm_id" -r "$REALM" --fields name --format csv --noquotes | sort | tr '\n' ' ')
  case " $ist " in *" view-users "*) ;; *) kc add-roles -r "$REALM" --uid "$sa" --cclientid realm-management --rolename view-users >/dev/null; echo "gesetzt:   Recht view-users für die Mitarbeiterkonten der Anwendung (nur lesen)" ;; esac
  for rolle in $ist; do
    case "$rolle" in
      view-users) ;;
      manage-users) kc remove-roles -r "$REALM" --uid "$sa" --cclientid realm-management --rolename manage-users >/dev/null
                    echo "entfernt:  Recht manage-users (Client konten) – ersetzt durch die Gruppe $KONTEN_GRUPPE, Administratoren nicht mehr über die Anwendung" ;;
      *) kc remove-roles -r "$REALM" --uid "$sa" --cclientid realm-management --rolename "$rolle" >/dev/null; echo "entfernt:  überzähliges Recht $rolle (Client konten)" ;;
    esac
  done
}

realm_aktualisieren() {
  command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
  kc update "realms/$REALM" -s ssoSessionIdleTimeout=14400 -s ssoSessionMaxLifespan=36000 >/dev/null
  echo "gesetzt:   Leerlauf 4 Stunden, höchstens 10 Stunden"
  # Neue Konten bekommen „Einmalcode einrichten“ nicht mehr automatisch (nur Pflicht-Konten, über die zweite Stufe)
  kc update "authentication/required-actions/CONFIGURE_TOTP" -r "$REALM" -s defaultAction=false >/dev/null
  # Optionaler zweiter Faktor in Stufe 1 (wer ihn eingerichtet hat, wird gefragt) – Aufbau wie Stufe 2
  if [ -z "$(ausf_id "e.get('displayName')=='mitarbeiter-optional-passkey'")" ]; then
    unterfluss mitarbeiter-stufe-1 mitarbeiter-optional-passkey "Passkey, wenn eingerichtet"
    schritt mitarbeiter-optional-passkey conditional-user-configured
    schritt mitarbeiter-optional-passkey webauthn-authenticator
  fi
  if [ -z "$(ausf_id "e.get('displayName')=='mitarbeiter-optional-einmalcode'")" ]; then
    unterfluss mitarbeiter-stufe-1 mitarbeiter-optional-einmalcode "Einmalcode, wenn eingerichtet und kein Passkey verwendet"
    schritt mitarbeiter-optional-einmalcode conditional-user-configured
    schritt mitarbeiter-optional-einmalcode conditional-credential '{"alias":"optional-ohne-passkey","config":{"credentials":"webauthn","included":"false"}}'
    schritt mitarbeiter-optional-einmalcode auth-otp-form
  fi
  # Reihenfolge festlegen (neue Ausführungen haben sonst Priorität 0 und liefen vor der Passwortabfrage)
  prioritaet mitarbeiter-stufe-1 mitarbeiter-optional-passkey 30
  prioritaet mitarbeiter-stufe-1 mitarbeiter-optional-einmalcode 40
  prioritaet mitarbeiter-optional-passkey conditional-user-configured 10
  prioritaet mitarbeiter-optional-passkey webauthn-authenticator 20
  prioritaet mitarbeiter-optional-einmalcode conditional-user-configured 10
  prioritaet mitarbeiter-optional-einmalcode conditional-credential 20
  prioritaet mitarbeiter-optional-einmalcode auth-otp-form 30
  # Anmeldemethoden im Claim amr (die Anwendung prüft damit den zweiten Faktor für Pflicht-Konten); gültig so lange wie
  # die Sitzung höchstens dauert (36000 s) – sonst fehlte der Nachweis bei Single Sign-on auf dem zweiten Host
  ausfuehrungen | python3 -c '
import json, sys
ref = {"auth-username-password-form": "pwd", "auth-otp-form": "otp", "webauthn-authenticator": "hwk"}
for e in json.load(sys.stdin):
    if e.get("providerId") in ref:
        print(e["id"], ref[e["providerId"]], e.get("authenticationConfig") or "-")' | while read -r id r cfg; do
    soll="{\"default.reference.value\":\"$r\",\"default.reference.maxAge\":\"36000\"}"
    if [ "$cfg" = - ]; then
      kc create "authentication/executions/$id/config" -r "$REALM" -b "{\"alias\":\"amr-$r-$(printf '%s' "$id" | cut -c1-8)\",\"config\":$soll}" >/dev/null
      echo "gesetzt:   amr '$r' für Ausführung $(printf '%s' "$id" | cut -c1-8)"
    elif kc get "authentication/config/$cfg" -r "$REALM" | python3 -c 'import json,sys; c=json.load(sys.stdin); sys.exit(0 if c["alias"].startswith("amr-") and c["config"].get("default.reference.maxAge") != "36000" else 1)'; then
      alias=$(kc get "authentication/config/$cfg" -r "$REALM" | python3 -c 'import json,sys; print(json.load(sys.stdin)["alias"])')
      kc update "authentication/config/$cfg" -r "$REALM" -b "{\"id\":\"$cfg\",\"alias\":\"$alias\",\"config\":$soll}" >/dev/null
      echo "angepasst: amr '$r' für Ausführung $(printf '%s' "$id" | cut -c1-8)"
    fi
  done
  # Alle Clients der Realm-Datei (dashboard, angebot, verwaltung, bestand, hr, crm, marketing, sicherheit, controlling, leergut, rewe, qs …): fehlende anlegen, dann einheitlich einstellen.
  # Ohne Realm-Datei (anderer Ordner) die bekannten Clients – fehlt einer davon, bricht client_anlegen mit Hinweis ab
  clients="dashboard angebot verwaltung bestand hr crm marketing sicherheit controlling leergut rewe qs konten"
  [ ! -f "$REALM_DATEI" ] || clients=$(python3 -c '
import json, re, sys
ids = [c.get("clientId", "") for c in json.load(open(sys.argv[1], encoding="utf-8")).get("clients", [])]
if not ids or not all(re.fullmatch(r"[a-z][a-z0-9-]{0,30}", i) for i in ids): sys.exit("ungültige Client-Namen")
print(" ".join(ids))' "$REALM_DATEI") || abbruch "Clients in $REALM_DATEI nicht lesbar."
  for c in $clients; do client_anlegen "$c"; done
  for c in $clients; do
    [ "$c" = konten ] && continue   # Service-Account: keine Anmeldestufe, kein amr-Claim
    cid=$(kc get clients -r "$REALM" -q clientId="$c" --fields id --format csv --noquotes | head -1)
    [ -n "$cid" ] || continue
    kc update "clients/$cid" -r "$REALM" -s 'attributes."default.acr.values"=pwd' -s 'attributes."minimum.acr.value"=pwd' >/dev/null
    # Ausgabe erst ganz lesen: „| grep -q“ schlösse die Leitung beim ersten Treffer, und docker compose exec bräche mit
    # SIGPIPE ab (Meldung „Abbruch: Keycloak hat den Befehl abgelehnt“, obwohl alles in Ordnung ist)
    mapper=$(kc get "clients/$cid/protocol-mappers/models" -r "$REALM")
    if ! printf '%s' "$mapper" | grep -q '"oidc-amr-mapper"'; then
      kc create "clients/$cid/protocol-mappers/models" -r "$REALM" -b '{"name":"amr","protocol":"openid-connect","protocolMapper":"oidc-amr-mapper","config":{"id.token.claim":"true","access.token.claim":"true","introspection.token.claim":"true","userinfo.token.claim":"true"}}' >/dev/null
      echo "angelegt:  amr-Claim für Client $c"
    fi
  done
  # Stand 14 (Härtung 03.11.2026): kein Client des Realms erlaubt den Passwort-Grant – auch keiner der Clients, die Keycloak
  # selbst anlegt. Anmeldungen laufen nur über die Anmeldeseite (Code-Ablauf); unsere Clients hatten ihn ohnehin aus.
  kc get clients -r "$REALM" --fields id,clientId,directAccessGrantsEnabled | python3 -c '
import json, sys
for c in json.load(sys.stdin):
    if c.get("directAccessGrantsEnabled"): print(c["id"], c["clientId"])' | while read -r id name; do
    kc update "clients/$id" -r "$REALM" -s directAccessGrantsEnabled=false >/dev/null
    echo "gesetzt:   Client $name ohne Passwort-Grant"
  done
  konten_rechte
  richtlinien_setzen
  echo "Realm aktuell (Stand 17: Client konten mit Scope kc-admin-api (Keycloak ab 26.8.2); Stand 16: Anwendung verwaltet nur Konten der Gruppe anwendungskonten, nie Administratoren; Stand 15: Passwortregeln und Kontosperre aus den Einstellungen der Anwendung; Stand 14: kein Passwort-Grant am Token-Endpunkt; Qualitätssicherung unter eigener Adresse; REWE unter eigener Adresse; Leergut unter eigener Adresse; Controlling unter eigener Adresse; Sicherheit unter eigener Adresse; Mitarbeiterkonten aus der Verwaltung; Marketing, CRM, HR, Bestand und Verwaltung unter eigener Adresse; zweiter Faktor nur für Pflicht-Konten, Leerlauf 4 Stunden)."
  if [ "$ENV_NEU" = 1 ]; then echo "Neue Werte in .env – die Anwendung liest sie nach: docker compose up -d app-mitarbeiter"; fi
}

pruefen() { # nur lesen: warum klappt die Anmeldung nicht? Konto, Sperre, zweiter Faktor, letzte Anmeldeereignisse, Uhrzeit
  [ $# -eq 1 ] || abbruch "Aufruf: konten.sh pruefen <benutzername>"
  name_pruefen "$1"; id=$(nutzer_id_pflicht "$1")
  d=$(mktemp -d); trap 'rm -rf "$d" "$FEHLER" "$FEHLER.client"' EXIT
  kc get "users/$id" -r "$REALM" >"$d/konto"
  kc get "users/$id/credentials" -r "$REALM" >"$d/faktoren"
  kc get "attack-detection/brute-force/users/$id" -r "$REALM" >"$d/sperre"
  kc get events -r "$REALM" -q user="$id" -q max=10 >"$d/ereignisse"
  kc get "realms/$REALM" --fields otpPolicyPeriod,otpPolicyLookAheadWindow,otpPolicyCodeReusable,failureFactor,eventsEnabled,browserFlow,attributes >"$d/realm"
  # Anmeldeablauf: meldet Keycloak den Einmalcode als Anmeldemethode (amr)? Sonst fordert die Anwendung bei Pflicht-Konten
  # eine zweite Stufe an – die Code-Maske erscheint dann ein zweites Mal
  kc get "authentication/flows/mitarbeiter-browser/executions" -r "$REALM" >"$d/ablauf"
  printf '[' >"$d/konfig"; k=
  for cfg in $(python3 -c 'import json,sys; print(" ".join(e["authenticationConfig"] for e in json.load(open(sys.argv[1])) if e.get("authenticationConfig")))' "$d/ablauf"); do
    printf '%s' "$k" >>"$d/konfig"; kc get "authentication/config/$cfg" -r "$REALM" >>"$d/konfig"; k=,
  done
  printf ']' >>"$d/konfig"
  # je Anwendung die Mapper einzeln (die Liste der Clients enthält sie nicht zuverlässig)
  printf '[' >"$d/clients"; k=
  for c in dashboard angebot verwaltung bestand hr crm marketing sicherheit controlling leergut rewe qs; do
    cid=$(kc get clients -r "$REALM" -q clientId="$c" --fields id --format csv --noquotes | head -1)
    [ -n "$cid" ] || continue
    attr=$(kc get "clients/$cid" -r "$REALM" --fields attributes)
    mapper=$(kc get "clients/$cid/protocol-mappers/models" -r "$REALM")
    printf '%s{"clientId":"%s","attributes":%s,"protocolMappers":%s}' "$k" "$c" \
      "$(printf '%s' "$attr" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin).get("attributes") or {}))')" "$mapper" >>"$d/clients"; k=,
  done
  printf ']' >>"$d/clients"
  # Uhrzeit: Einmalcodes hängen an der Serveruhr (Container nutzen die Uhr des Servers); Vergleich mit einer Zeitquelle
  quelle=${ZEIT_QUELLE:-https://github.com}
  fremd=$(curl -sSI --max-time 5 "$quelle" 2>/dev/null | sed -n 's/^[Dd]ate: *//p' | tr -d '\r' | head -1) || fremd=
  ntp=$(timedatectl show -p NTPSynchronized --value 2>/dev/null) || ntp=
  NAME="$1" FREMD="$fremd" NTP="$ntp" QUELLE="$quelle" python3 - "$d" <<'PY'
import json, os, sys, time
from email.utils import parsedate_to_datetime
d = sys.argv[1]
lade = lambda n: json.load(open(os.path.join(d, n)))
konto, faktoren, sperre, ereignisse, realm = lade('konto'), lade('faktoren'), lade('sperre'), lade('ereignisse'), lade('realm')
ablauf, konfig, clients = lade('ablauf'), {c.get('id'): c for c in lade('konfig')}, lade('clients')
zeit = lambda ms: time.strftime('%d.%m.%Y %H:%M:%S', time.localtime(ms / 1000)) if ms else '–'
hinweise = []
print(f"Konto '{os.environ['NAME']}': {'aktiv' if konto.get('enabled') else 'GESPERRT (konten.sh entsperren)'}")
if konto.get('requiredActions'):
    print('  offene Schritte bei der nächsten Anmeldung:', ', '.join(konto['requiredActions']))
print('Automatische Sperre nach Fehlversuchen:', 'JA, vorübergehend gesperrt' if sperre.get('disabled') else 'nein',
      f"· Fehlversuche in Folge: {sperre.get('numFailures', 0)} (Grenze {realm.get('failureFactor', '?')})",
      f"· letzter Fehlversuch: {zeit(sperre.get('lastFailure'))}")
if sperre.get('disabled'):
    hinweise.append('Sperre aufheben: sh deploy/anmeldung/konten.sh entsperren ' + os.environ['NAME'])
arten = {'password': 'Passwort', 'otp': 'Einmalcode (App)', 'webauthn': 'Passkey', 'webauthn-passwordless': 'Passkey (ohne Passwort)'}
print('Anmeldefaktoren:')
for f in faktoren:
    print(f"  - {arten.get(f.get('type'), f.get('type'))}: eingerichtet {zeit(f.get('createdDate'))}"
          + (f" · Bezeichnung „{f['userLabel']}“" if f.get('userLabel') else ''))
otp = [f for f in faktoren if f.get('type') == 'otp']
if len(otp) > 1:
    hinweise.append(f'{len(otp)} Einmalcode-Geräte eingerichtet: die Anmeldeseite fragt den Code des dort ausgewählten Geräts ab – '
                    'ein Code aus einem anderen App-Eintrag gilt als falsch. Am einfachsten: konten.sh zuruecksetzen, in der App '
                    'alle Einträge „STAFL-Plattform“ löschen und neu einrichten.')
print(f"Einmalcode-Regeln: wechselt alle {realm.get('otpPolicyPeriod', 30)} s, Toleranz ±{realm.get('otpPolicyLookAheadWindow', 1)} Schritt(e), "
      + ('mehrfach verwendbar' if realm.get('otpPolicyCodeReusable') else 'jeder Code nur einmal (nach einem Fehlschlag auf den nächsten Code warten)'))
fehler_text = {
    'invalid_user_credentials': 'Passwort oder Einmalcode falsch (auch: Code schon benutzt, falscher App-Eintrag, Uhr verstellt)',
    'user_temporarily_disabled': 'vorübergehend gesperrt nach Fehlversuchen',
    'user_disabled': 'Konto gesperrt',
    'user_not_found': 'Benutzername unbekannt',
    'expired_code': 'Anmeldeseite zu lange offen – neu laden',
    'invalid_code': 'Anmeldevorgang abgelaufen oder doppelt abgeschickt',
    'cookie_not_found': 'Browser hat das Anmelde-Cookie nicht mitgeschickt (privates Fenster/Cookies prüfen)',
}
print('Letzte Anmeldeereignisse (neueste zuerst):')
if not ereignisse:
    print('  keine gespeichert' + ('' if realm.get('eventsEnabled') else ' (Ereignisprotokoll ist aus)'))
for e in ereignisse:
    det = e.get('details') or {}
    teil = [zeit(e.get('time')), e.get('type', '?')]
    if e.get('error'):
        teil.append(fehler_text.get(e['error'], e['error']))
    if det.get('credential_type') or det.get('auth_method'):
        teil.append('Schritt: ' + str(det.get('credential_type') or det.get('auth_method')))
    if e.get('clientId'):
        teil.append('über ' + e['clientId'])
    if e.get('ipAddress'):
        teil.append('von ' + e['ipAddress'])
    print('  - ' + ' · '.join(teil))
print('Anmeldeablauf (gemeldete Anmeldemethoden, amr):')
art = {'auth-username-password-form': 'Passwort', 'auth-otp-form': 'Einmalcode', 'webauthn-authenticator': 'Passkey'}
for e in ablauf:
    if e.get('providerId') in art:
        c = (konfig.get(e.get('authenticationConfig')) or {}).get('config') or {}
        ref, alter = c.get('default.reference.value'), c.get('default.reference.maxAge')
        print(f"  - {art[e['providerId']]} (Ebene {e.get('level')}, {e.get('requirement')}): " + (f"meldet '{ref}', gültig {alter or '?'} s" if ref else 'meldet NICHTS'))
        if not ref:
            hinweise.append(f"{art[e['providerId']]} (Ebene {e.get('level')}) wird nicht als Anmeldemethode gemeldet – die Anwendung erkennt ihn nicht und fragt den zweiten Faktor ein zweites Mal ab. Abhilfe: sh deploy/anmeldung/konten.sh realm-aktualisieren")
print('Anwendungen (Clients):')
for c in sorted(clients, key=lambda c: c.get('clientId', '')):
    if c.get('clientId') not in ('dashboard', 'angebot', 'verwaltung', 'bestand'):
        continue
    amr = [m for m in c.get('protocolMappers') or [] if m.get('protocolMapper') == 'oidc-amr-mapper']
    im_token = any((m.get('config') or {}).get('id.token.claim') == 'true' for m in amr)
    acr = (c.get('attributes') or {}).get('default.acr.values', '–')
    print(f"  - {c['clientId']}: amr-Claim " + ('im Anmelde-Token' if im_token else ('vorhanden, aber NICHT im Anmelde-Token' if amr else 'FEHLT')) + f" · Standard-Stufe {acr}")
    if not im_token:
        hinweise.append(f"Client {c['clientId']}: Anmeldemethoden fehlen im Anmelde-Token – Abhilfe: sh deploy/anmeldung/konten.sh realm-aktualisieren")
jetzt = time.time()
print('Serveruhr:', time.strftime('%d.%m.%Y %H:%M:%S %Z', time.localtime(jetzt)),
      '· mit Zeitserver abgeglichen:', {'yes': 'ja', 'no': 'NEIN'}.get(os.environ.get('NTP', ''), 'unbekannt'))
if os.environ.get('FREMD'):
    try:
        abw = jetzt - parsedate_to_datetime(os.environ['FREMD']).timestamp()
        print(f"  Abweichung gegenüber {os.environ['QUELLE']}: {abw:+.0f} s")
        if abs(abw) > 15:
            hinweise.append(f'Serveruhr weicht {abw:+.0f} s ab – Einmalcodes werden dann abgelehnt. Uhr synchronisieren (timedatectl).')
    except (TypeError, ValueError):
        pass
if os.environ.get('NTP') == 'no':
    hinweise.append('Serveruhr wird nicht mit einem Zeitserver abgeglichen (timedatectl set-ntp true).')
print('Hinweise:' if hinweise else 'Keine Auffälligkeiten gefunden.')
for h in hinweise:
    print('  * ' + h)
PY
}

# ── Passwort vergessen (Stand 14, Inhaber 03.11.2026) ──
# Eigener Ablauf statt des eingebauten „reset credentials“: Der eingebaute enthält „Reset OTP“ (entfernt den Einmalcode) –
# dann übernähme, wer an das Postfach kommt, ein Administratorkonto samt zweitem Faktor. Hier verlangt der Ablauf nach dem
# Link aus der Mail den eingerichteten zweiten Faktor (Passkey oder Einmalcode, wie bei der Anmeldung), erst danach das neue
# Passwort; Einmalcode und Passkeys bleiben. Wer keinen zweiten Faktor hat, setzt nur das Passwort neu.
# Gleicher Aufbau wie in der Realm-Datei (authenticationFlows, resetCredentialsFlow) – die CI vergleicht beides.
VERGESSEN=mitarbeiter-passwort-vergessen
VERGESSEN_LINK_SEKUNDEN=900
vergessen_aufbau() { # Aufbau des Ablaufs als eine Zeile je Ausführung: Ebene|Anbieter oder Unterablauf|Anforderung|Priorität
  kc get "authentication/flows/$VERGESSEN/executions" -r "$REALM" | python3 -c '
import json, sys
for e in json.load(sys.stdin):
    print("%s|%s|%s|%s" % (e["level"], e.get("providerId") or e.get("displayName"), e["requirement"], e.get("priority")))'
}
VERGESSEN_SOLL="0|reset-credentials-choose-user|REQUIRED|10
0|reset-credential-email|REQUIRED|20
0|mitarbeiter-vergessen-passkey|CONDITIONAL|30
1|conditional-user-configured|REQUIRED|10
1|webauthn-authenticator|REQUIRED|20
0|mitarbeiter-vergessen-einmalcode|CONDITIONAL|40
1|conditional-user-configured|REQUIRED|10
1|conditional-credential|REQUIRED|20
1|auth-otp-form|REQUIRED|30
0|reset-password|REQUIRED|50"
vergessen_schritt() { # vergessen_schritt <ablauf> <provider> <anforderung> <priorität> [<config-json>]
  kc create "authentication/flows/$1/executions/execution" -r "$REALM" -b "{\"provider\":\"$2\"}" >/dev/null
  id=$(kc get "authentication/flows/$1/executions" -r "$REALM" | python3 -c "import json,sys; es=json.load(sys.stdin); top=min(e['level'] for e in es); print([e['id'] for e in es if e['level']==top and e.get('providerId')=='$2'][-1])")
  kc update "authentication/flows/$1/executions" -r "$REALM" -b "{\"id\":\"$id\",\"requirement\":\"$3\",\"priority\":$4}" >/dev/null
  if [ -n "${5:-}" ]; then kc create "authentication/executions/$id/config" -r "$REALM" -b "$5" >/dev/null; fi
}
vergessen_unterablauf() { # vergessen_unterablauf <alias> <beschreibung> <priorität>
  kc create "authentication/flows/$VERGESSEN/executions/flow" -r "$REALM" -b "{\"alias\":\"$1\",\"type\":\"basic-flow\",\"provider\":\"registration-page-form\",\"description\":\"$2\"}" >/dev/null
  id=$(kc get "authentication/flows/$VERGESSEN/executions" -r "$REALM" | python3 -c "import json,sys; print([e['id'] for e in json.load(sys.stdin) if e.get('displayName')=='$1' and e.get('authenticationFlow')][0])")
  kc update "authentication/flows/$VERGESSEN/executions" -r "$REALM" -b "{\"id\":\"$id\",\"requirement\":\"CONDITIONAL\",\"priority\":$3}" >/dev/null
}
vergessen_anlegen() {
  kc create authentication/flows -r "$REALM" -b "{\"alias\":\"$VERGESSEN\",\"providerId\":\"basic-flow\",\"topLevel\":true,\"builtIn\":false,\"description\":\"Passwort vergessen: Link per Mail, zweiter Faktor wenn eingerichtet, dann neues Passwort (ohne Reset OTP)\"}" >/dev/null
  vergessen_schritt "$VERGESSEN" reset-credentials-choose-user REQUIRED 10
  vergessen_schritt "$VERGESSEN" reset-credential-email REQUIRED 20
  vergessen_unterablauf mitarbeiter-vergessen-passkey "Passkey, wenn eingerichtet" 30
  vergessen_schritt mitarbeiter-vergessen-passkey conditional-user-configured REQUIRED 10
  vergessen_schritt mitarbeiter-vergessen-passkey webauthn-authenticator REQUIRED 20 '{"alias":"amr-hwk-vergessen","config":{"default.reference.value":"hwk","default.reference.maxAge":"36000"}}'
  vergessen_unterablauf mitarbeiter-vergessen-einmalcode "Einmalcode, wenn eingerichtet und kein Passkey verwendet" 40
  vergessen_schritt mitarbeiter-vergessen-einmalcode conditional-user-configured REQUIRED 10
  vergessen_schritt mitarbeiter-vergessen-einmalcode conditional-credential REQUIRED 20 '{"alias":"vergessen-ohne-passkey","config":{"credentials":"webauthn","included":"false"}}'
  vergessen_schritt mitarbeiter-vergessen-einmalcode auth-otp-form REQUIRED 30 '{"alias":"amr-otp-vergessen","config":{"default.reference.value":"otp","default.reference.maxAge":"36000"}}'
  vergessen_schritt "$VERGESSEN" reset-password REQUIRED 50
  echo "angelegt:  Ablauf $VERGESSEN (zweiter Faktor bleibt Pflicht, wenn eingerichtet)"
}
passwort_vergessen() {
  [ $# -eq 1 ] || abbruch "Aufruf: konten.sh passwort-vergessen an|aus|status"
  case "$1" in an|aus|status) ;; *) abbruch "Aufruf: konten.sh passwort-vergessen an|aus|status" ;; esac
  bereit
  command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
  # Ausgaben erst ganz lesen (docker compose exec, siehe realm_aktualisieren)
  # smtpServer nur mit Unterfeld (sonst liefert --fields ein leeres Objekt); das Passwort steht ohnehin nur als Verweis/Maske darin
  realm=$(kc get "realms/$REALM" --fields 'resetPasswordAllowed,resetCredentialsFlow,smtpServer(host)')
  an=$(printf '%s' "$realm" | python3 -c 'import json,sys; print("ja" if json.load(sys.stdin).get("resetPasswordAllowed") else "nein")')
  ablauf=$(printf '%s' "$realm" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("resetCredentialsFlow") or "")')
  mail=$(printf '%s' "$realm" | python3 -c 'import json,sys; print("ja" if (json.load(sys.stdin).get("smtpServer") or {}).get("host") else "nein")')
  vorhanden=$(kc get authentication/flows -r "$REALM" | python3 -c "import json,sys; print('ja' if any(f.get('alias')=='$VERGESSEN' for f in json.load(sys.stdin)) else 'nein')")
  case "$1" in
    status)
      if [ "$an" = ja ]; then echo "Passwort vergessen: an (Link auf der Anmeldeseite)"; else echo "Passwort vergessen: aus"; fi
      if [ "$ablauf" = "$VERGESSEN" ] && [ "$vorhanden" = ja ] && [ "$(vergessen_aufbau)" = "$VERGESSEN_SOLL" ]; then
        echo "Ablauf: $VERGESSEN – zweiter Faktor bleibt Pflicht, wenn eingerichtet (abgesichert)"
      else
        echo "Ablauf: ${ablauf:-Keycloak-Standard} – NICHT abgesichert (beim Einschalten wird der eigene Ablauf gesetzt)"
      fi
      if [ "$mail" = ja ]; then echo "Mailversand der Anmeldung: eingerichtet"; else echo "Mailversand der Anmeldung: fehlt (konten.sh mail-einrichten)"; fi
      ;;
    an)
      [ "$mail" = ja ] || abbruch "Keycloak kann noch keine E-Mails senden – zuerst: sh deploy/anmeldung/konten.sh mail-einrichten [<test-adresse>]"
      if [ "$vorhanden" = nein ]; then vergessen_anlegen
      elif [ "$(vergessen_aufbau)" != "$VERGESSEN_SOLL" ]; then
        abbruch "Der Ablauf $VERGESSEN in Keycloak weicht vom vorgesehenen Aufbau ab (von Hand geändert?) – nicht eingeschaltet. Aufbau: konten.sh passwort-vergessen status"
      fi
      # Link aus der Mail 15 Minuten gültig (Keycloak-Standard 5 Minuten – zu knapp, wenn die Mail etwas braucht)
      kc update "realms/$REALM" -s resetCredentialsFlow="$VERGESSEN" -s resetPasswordAllowed=true \
        -s "attributes.\"actionTokenGeneratedByUserLifespan.reset-credentials\"=$VERGESSEN_LINK_SEKUNDEN" >/dev/null
      echo "eingeschaltet: Link 'Passwort vergessen?' auf der Anmeldeseite – Link per Mail, $((VERGESSEN_LINK_SEKUNDEN / 60)) Minuten gültig (zweiter Faktor bleibt Pflicht, wenn eingerichtet)"
      ;;
    aus)
      kc update "realms/$REALM" -s resetPasswordAllowed=false >/dev/null
      echo "ausgeschaltet: kein Link 'Passwort vergessen?' mehr – vergessene Passwörter wie bisher: konten.sh startpasswort <name> oder Verwaltung → Mitarbeiter"
      ;;
  esac
}

# ── Passwortregeln und Kontosperre aus der Anwendung (Stand 15, Inhaber 04.11.2026) ──
# Quelle ist Sicherheit → Einstellungen → Anmeldung und Passwörter (eine Stelle für alles). Keycloak übernimmt: Mindestlänge
# (nie unter 12, dem bisherigen Grundwert), „gemischte Zeichen“ (dann Groß- und Kleinbuchstabe und Ziffer), Sperre nach
# Fehlversuchen und deren Dauer je Konto. Bleibt wie bisher: nicht Benutzername/E-Mail, keins der letzten 3 Passwörter.
# Die Prüfung gegen Datenlecks kann Keycloak nicht. Die Anwendung selbst hat für die Konten nur die Rechte view-users und
# manage-users – deshalb übernimmt das dieser Befehl (auch in realm-aktualisieren), nach jeder Änderung der Einstellungen.
richtlinien_werte() { # Ausgabe: <passwordPolicy>|<failureFactor>|<Sperre in Sekunden>|<Text>
  app sicherheit | python3 -c '
import json, sys
s = json.load(sys.stdin)
n = max(12, min(32, int(s["pwMin"])))
pol = "length(%d) and notUsername and notEmail and passwordHistory(3)" % n
if s.get("pwComplex"): pol += " and upperCase(1) and lowerCase(1) and digits(1)"
f = max(3, min(20, int(s["lockAfter"]))); m = max(5, min(1440, int(s["lockMinutes"])))
print("%s|%d|%d|Passwörter mindestens %d Zeichen%s, Sperre nach %d Fehlversuchen für %d Minuten" % (pol, f, 60 * m, n, " (Groß-, Kleinbuchstabe und Ziffer)" if s.get("pwComplex") else "", f, m))'
}
richtlinien_setzen() { # ohne lesbare Anwendung: Hinweis, nichts geändert
  werte=$(richtlinien_werte 2>/dev/null) || { echo "Hinweis:   Einstellungen der Anwendung nicht lesbar – Passwortregeln und Kontosperre unverändert (später: konten.sh richtlinien)."; return 0; }
  pol=${werte%%|*}; rest=${werte#*|}; ff=${rest%%|*}; rest=${rest#*|}; sek=${rest%%|*}; text=${rest#*|}
  if kc get "realms/$REALM" --fields passwordPolicy,bruteForceProtected,permanentLockout,failureFactor,waitIncrementSeconds,maxFailureWaitSeconds \
     | SOLL="$pol|$ff|$sek" python3 -c '
import json, os, sys
r = json.load(sys.stdin); pol, ff, sek = os.environ["SOLL"].split("|")
norm = lambda p: " and ".join(t.strip().replace("(undefined)", "") for t in (p or "").split(" and "))
ok = norm(r.get("passwordPolicy")) == norm(pol) and r.get("bruteForceProtected") is True and r.get("permanentLockout") is False \
     and r.get("failureFactor") == int(ff) and r.get("waitIncrementSeconds") == int(sek) and r.get("maxFailureWaitSeconds") == int(sek)
sys.exit(0 if ok else 1)'; then
    echo "aktuell:   $text"
  else
    kc update "realms/$REALM" -s "passwordPolicy=$pol" -s bruteForceProtected=true -s permanentLockout=false \
      -s "failureFactor=$ff" -s "waitIncrementSeconds=$sek" -s "maxFailureWaitSeconds=$sek" >/dev/null
    echo "gesetzt:   $text"
  fi
}
richtlinien() {
  command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
  app sicherheit >/dev/null 2>&1 || abbruch "Einstellungen der Anwendung nicht lesbar (läuft die App?)."
  richtlinien_setzen
  echo "Gilt ab der nächsten Anmeldung bzw. Passwortänderung; bestehende Passwörter bleiben gültig."
}

# ── Konten ohne Mitarbeiter (Inhaber 04.11.2026) ──
# Seit 04.11.2026 löscht die Anwendung das Konto mit, wenn ein Mitarbeiter gelöscht wird. Ältere Konten gelöschter
# Mitarbeiter blieben bestehen – ein später gleich benannter Mitarbeiter wäre damit verknüpft worden. „verwaist“ zeigt
# Konten, zu denen es kein Mitarbeiterkonto gibt (nicht verknüpft und kein gleich benannter, noch nicht verknüpfter
# Mitarbeiter) sowie Konten, die als gelöscht vermerkt sind; „--loeschen“ löscht genau diese.
verwaist() {
  case "${1:-}" in "") loeschen=0 ;; --loeschen) loeschen=1 ;; *) abbruch "Aufruf: konten.sh verwaist [--loeschen]" ;; esac
  [ $# -le 1 ] || abbruch "Aufruf: konten.sh verwaist [--loeschen]"
  command -v python3 >/dev/null || abbruch "python3 fehlt auf dem Server."
  app_konten=$(app konten) || abbruch "Mitarbeiterkonten der Anwendung nicht lesbar (läuft die App?)."
  ohne=$(kc get users -r "$REALM" --offset 0 --limit 5000 --fields id,username,createdTimestamp | APP_KONTEN="$app_konten" python3 -c '
import json, os, sys, time
a = json.loads(os.environ["APP_KONTEN"])
subs = {k["sub"] for k in a["konten"] if k["sub"]}
namen = {k["name"] for k in a["konten"] if not k["sub"]}
weg = set(a["geloescht"])
for u in json.load(sys.stdin):
    n = u.get("username", "")
    if n.startswith("service-account-") or u["id"] in subs or (n in namen and u["id"] not in weg): continue
    print(u["id"], n, time.strftime("%d.%m.%Y", time.localtime(u.get("createdTimestamp", 0) / 1000)))')
  if [ -z "$ohne" ]; then echo "Keine Konten ohne Mitarbeiter – nichts zu tun."; return 0; fi
  printf '%s\n' "$ohne" | while read -r id n datum; do
    if [ "$loeschen" = 1 ]; then
      kc delete "users/$id" -r "$REALM" >/dev/null
      echo "gelöscht:  Konto '$n' (angelegt $datum)"
    else
      echo "ohne Mitarbeiter: Konto '$n' (angelegt $datum)"
    fi
  done
  [ "$loeschen" = 1 ] || echo "Löschen (genau diese Konten): sh deploy/anmeldung/konten.sh verwaist --loeschen"
}

liste() {
  echo "benutzername,vorname,nachname,e-mail,aktiv"
  kc get users -r "$REALM" --fields username,firstName,lastName,email,enabled --format csv --noquotes
}

befehl=${1:-}; [ $# -gt 0 ] && shift
if [ $# -gt 0 ]; then n=$(klein "$1"); shift; set -- "$n" "$@"; fi
case "$befehl" in anlegen|startpasswort|zuruecksetzen|passkey|sperren|entsperren|pruefen|liste|mail-einrichten|einladen|realm-aktualisieren|richtlinien|verwaist|gruppe-abgleichen) bereit ;; esac
case "$befehl" in
  verwaltung) verwaltung ;;
  anlegen) anlegen "$@" ;;
  startpasswort) startpasswort_neu "$@" ;;
  zuruecksetzen) zuruecksetzen "$@" ;;
  passkey) passkey "$@" ;;
  sperren) sperren "$@" ;;
  entsperren) entsperren "$@" ;;
  pruefen) pruefen "$@" ;;
  liste) liste ;;
  mail-einrichten) mail_einrichten "$@" ;;
  einladen) einladen "$@" ;;
  design-setzen) design_setzen "$@" ;;
  realm-aktualisieren) realm_aktualisieren ;;
  passwort-vergessen) passwort_vergessen "$@" ;;
  richtlinien) richtlinien ;;
  verwaist) verwaist "$@" ;;
  gruppe-abgleichen) gruppe_abgleichen_befehl "$@" ;;
  *) sed -n '2,/^set -eu/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
