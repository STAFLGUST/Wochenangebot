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
#   sh deploy/anmeldung/konten.sh einladen <benutzername> <e-mail> <vorname> <nachname>   # Konto anlegen und einladen
#   sh deploy/anmeldung/konten.sh einladen <benutzername>         # Einladung erneut senden
#   sh deploy/anmeldung/konten.sh realm-aktualisieren             # Realm auf den aktuellen Stand bringen (idempotent)
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
APP_PHP=${APP_PHP:-docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml exec -T -u www-data app php}
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
# Startpasswort: gut vorlesbar (keine 0/O/1/l/I), 16 Zeichen in Vierergruppen; Realm verlangt mindestens 12
startpasswort() { tr -dc 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789' < /dev/urandom | head -c 16 | sed 's/\(....\)/\1-/g; s/-$//'; }

kc_als() { # kc_als <benutzer> <passwort> <kcadm-Befehl…>
  u=$1; p=$2; shift 2
  # shellcheck disable=SC2086  # KCADM ist bewusst ein Befehl mit Argumenten
  $KCADM "$@" --no-config --server "$KC_SERVER" --realm master --user "$u" --password "$p" 2>"$FEHLER"
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
  neues_startpasswort "$1"
}

neues_startpasswort() {
  sp=$(startpasswort)
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
      -s enabled=true -s emailVerified=true -s 'requiredActions=["UPDATE_PASSWORD"]' >/dev/null
    id=$(nutzer_id "$1"); echo "angelegt:  Konto '$1'"
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

# Client eines neuen Hosts anlegen (Stand 3: verwaltung, Stand 4: bestand). Definition aus der Realm-Datei, Geheimnisse aus .env – fehlen sie,
# werden sie wie von einrichten.sh erzeugt (nie angezeigt). Danach liest die Anwendung sie erst nach einem Neustart.
ENV_NEU=0
client_anlegen() { # client_anlegen <clientId>
  c=$1; n=$(printf '%s' "$1" | tr 'a-z' 'A-Z')
  [ -n "$(kc get clients -r "$REALM" -q clientId="$c" --fields id --format csv --noquotes | head -1)" ] && return 0
  [ -f "$REALM_DATEI" ] || abbruch "$REALM_DATEI fehlt – Stand von main einspielen."
  for g in SECRET CRYPTO; do
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
  # Alle Clients der Realm-Datei (dashboard, angebot, verwaltung, bestand …): fehlende anlegen, dann einheitlich einstellen.
  # Ohne Realm-Datei (anderer Ordner) die bekannten Clients – fehlt einer davon, bricht client_anlegen mit Hinweis ab
  clients="dashboard angebot verwaltung bestand"
  [ ! -f "$REALM_DATEI" ] || clients=$(python3 -c '
import json, re, sys
ids = [c.get("clientId", "") for c in json.load(open(sys.argv[1], encoding="utf-8")).get("clients", [])]
if not ids or not all(re.fullmatch(r"[a-z][a-z0-9-]{0,30}", i) for i in ids): sys.exit("ungültige Client-Namen")
print(" ".join(ids))' "$REALM_DATEI") || abbruch "Clients in $REALM_DATEI nicht lesbar."
  for c in $clients; do client_anlegen "$c"; done
  for c in $clients; do
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
  echo "Realm aktuell (Stand 4: Bestand und Verwaltung unter eigener Adresse; zweiter Faktor nur für Pflicht-Konten, Leerlauf 4 Stunden)."
  if [ "$ENV_NEU" = 1 ]; then echo "Neue Werte in .env – die Anwendung liest sie nach: docker compose up -d app"; fi
}

pruefen() { # nur lesen: warum klappt die Anmeldung nicht? Konto, Sperre, zweiter Faktor, letzte Anmeldeereignisse, Uhrzeit
  [ $# -eq 1 ] || abbruch "Aufruf: konten.sh pruefen <benutzername>"
  name_pruefen "$1"; id=$(nutzer_id_pflicht "$1")
  d=$(mktemp -d); trap 'rm -rf "$d" "$FEHLER" "$FEHLER.client"' EXIT
  kc get "users/$id" -r "$REALM" >"$d/konto"
  kc get "users/$id/credentials" -r "$REALM" >"$d/faktoren"
  kc get "attack-detection/brute-force/users/$id" -r "$REALM" >"$d/sperre"
  kc get events -r "$REALM" -q user="$id" -q max=10 >"$d/ereignisse"
  kc get "realms/$REALM" --fields otpPolicyPeriod,otpPolicyLookAheadWindow,otpPolicyCodeReusable,failureFactor,eventsEnabled >"$d/realm"
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

liste() {
  echo "benutzername,vorname,nachname,e-mail,aktiv"
  kc get users -r "$REALM" --fields username,firstName,lastName,email,enabled --format csv --noquotes
}

befehl=${1:-}; [ $# -gt 0 ] && shift
if [ $# -gt 0 ]; then n=$(klein "$1"); shift; set -- "$n" "$@"; fi
case "$befehl" in anlegen|startpasswort|zuruecksetzen|passkey|sperren|entsperren|pruefen|liste|mail-einrichten|einladen|realm-aktualisieren) bereit ;; esac
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
  realm-aktualisieren) realm_aktualisieren ;;
  *) sed -n '2,/^set -eu/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
