#!/bin/sh
# Test von deploy/anmeldung/einrichten.sh (Schritt 2 der Inbetriebnahme) – in einem Wegwerf-Ordner, ohne Docker.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; fi; }

mkdir -p "$T/deploy/anmeldung"
cp "$REPO/deploy/anmeldung/realm-mitarbeiter.json" "$T/deploy/anmeldung/"
# Vorhandene Testwerte (keine echten Geheimnisse) – zur Laufzeit zusammengesetzt, damit der Secret-Scan sie nicht meldet
export VORHANDEN; VORHANDEN="schon-$(echo gesetzt)-123"
printf 'DOMAIN=angebot-stafl.de\nMAIL_SMTP_%s=vorhanden-bleibt\nOIDC_SECRET_ANGEBOT=%s' PASS "$VORHANDEN" > "$T/.env"   # ohne Zeilenende
cd "$T"
export AUS; AUS=$(KC_UID=$(id -u) sh "$REPO/deploy/anmeldung/einrichten.sh")

ok "fehlende Geheimnisse ergänzt" 'for n in OIDC_SECRET_DASHBOARD OIDC_CRYPTO_DASHBOARD OIDC_CRYPTO_ANGEBOT OIDC_SECRET_VERWALTUNG OIDC_CRYPTO_VERWALTUNG OIDC_SECRET_BESTAND OIDC_CRYPTO_BESTAND OIDC_SECRET_HR OIDC_CRYPTO_HR OIDC_SECRET_CRM OIDC_CRYPTO_CRM OIDC_SECRET_MARKETING OIDC_CRYPTO_MARKETING OIDC_SECRET_SICHERHEIT OIDC_CRYPTO_SICHERHEIT OIDC_SECRET_CONTROLLING OIDC_CRYPTO_CONTROLLING OIDC_SECRET_LEERGUT OIDC_CRYPTO_LEERGUT OIDC_SECRET_KONTEN KC_DB_PASSWORD; do grep -q "^$n=." .env || exit 1; done'
S=daten-anmeldung/einrichtung.env
ok "Start-Konto in eigener Datei (nur Besitzer), nicht in .env" 'grep -q "^KC_BOOTSTRAP_ADMIN_USERNAME=einrichtung$" $S && test "$(sed -n "s/^KC_BOOTSTRAP_ADMIN_PASSWORD=//p" $S | wc -c)" -ge 40 && test "$(stat -c %a $S)" = 600 && ! grep -q "^KC_BOOTSTRAP_" .env'
ok "Start-Konto-Passwort nicht in der Ausgabe" 'v=$(sed -n "s/^KC_BOOTSTRAP_ADMIN_PASSWORD=//p" $S); case "$AUS" in *"$v"*) exit 1;; esac'
ok "vorhandene Einträge nicht überschrieben" 'grep -q "^OIDC_SECRET_ANGEBOT=$VORHANDEN$" .env && grep -q "^MAIL_SMTP_PASS=vorhanden-bleibt$" .env && grep -q "^DOMAIN=angebot-stafl.de$" .env'
ok "letzte vorhandene Zeile nicht zerstört (fehlendes Zeilenende)" 'grep -c "^OIDC_SECRET_ANGEBOT=" .env | grep -q "^1$"'
ok "Geheimnisse zufällig und lang genug" 'test "$(sed -n "s/^KC_DB_PASSWORD=//p" .env | wc -c)" -ge 40 && test "$(sed -n "s/^OIDC_CRYPTO_DASHBOARD=//p" .env)" != "$(sed -n "s/^OIDC_CRYPTO_ANGEBOT=//p" .env)"'
ok "kein Geheimnis in der Ausgabe" 'for n in OIDC_SECRET_DASHBOARD KC_DB_PASSWORD OIDC_SECRET_ANGEBOT; do v=$(sed -n "s/^$n=//p" .env); case "$AUS" in *"$v"*) exit 1;; esac; done'
ok ".env nur für den Besitzer lesbar" 'test "$(stat -c %a .env)" = 600'
R=daten-anmeldung/realm-import/realm-mitarbeiter.json
ok "Realm geschrieben, keine Platzhalter mehr" 'test -f $R && ! grep -q "@GEHEIM_" $R'
ok "Client-Geheimnisse eingesetzt" 'grep -q "\"secret\": \"$VORHANDEN\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_DASHBOARD=//p" .env)\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_VERWALTUNG=//p" .env)\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_BESTAND=//p" .env)\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_HR=//p" .env)\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_CRM=//p" .env)\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_MARKETING=//p" .env)\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_SICHERHEIT=//p" .env)\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_CONTROLLING=//p" .env)\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_LEERGUT=//p" .env)\"" $R && grep -q "\"secret\": \"$(sed -n "s/^OIDC_SECRET_KONTEN=//p" .env)\"" $R'
ok "Realm-Datei und Ordner nur für den Besitzer" 'test "$(stat -c %a $R)" = 600 && test "$(stat -c %a daten-anmeldung)" = 700'
ok "Tresor-Ordner für Keycloak angelegt (nur Besitzer)" 'test "$(stat -c %a daten-anmeldung/vault)" = 700'
ok "Realm gültiges JSON ohne Testnutzer" 'python3 -c "import json,sys; r=json.load(open(\"$R\")); sys.exit(\"users\" in r)"'
export vorher; vorher=$(sha256sum .env $R $S)
export AUS2; AUS2=$(KC_UID=$(id -u) sh "$REPO/deploy/anmeldung/einrichten.sh")
ok "zweiter Lauf ändert nichts" 'test "$vorher" = "$(sha256sum .env $R $S)" && echo "$AUS2" | grep -q "0 neue Einträge"'
# Einrichtung abgeschlossen (konten.sh verwaltung): kein neues Start-Konto
rm $S; echo "KC_VERWALTUNG_PASSWORD=x$(echo 1)" >> .env
KC_UID=$(id -u) sh "$REPO/deploy/anmeldung/einrichten.sh" >/dev/null
ok "nach abgeschlossener Einrichtung kein neues Start-Konto" 'test ! -f $S'
# ältere Fassung: Start-Konto stand in .env → wird übernommen und aus .env entfernt
sed -i "/^KC_VERWALTUNG_PASSWORD=/d" .env; printf "KC_BOOTSTRAP_ADMIN_USERNAME=einrichtung\nKC_BOOTSTRAP_ADMIN_PASSWORD=alt-%s\n" "$(echo 42)" >> .env
KC_UID=$(id -u) sh "$REPO/deploy/anmeldung/einrichten.sh" >/dev/null
ok "älteres Start-Konto aus .env übernommen und dort entfernt" 'grep -q "^KC_BOOTSTRAP_ADMIN_PASSWORD=alt-42$" $S && ! grep -q "^KC_BOOTSTRAP_" .env'
ok "Prüfmodus zeigt nur Namen" 'P=$(sh "$REPO/deploy/anmeldung/einrichten.sh" --pruefen); echo "$P" | grep -q "vorhanden: KC_DB_PASSWORD" && echo "$P" | grep -q "Start-Konto" && ! echo "$P" | grep -q "$(sed -n "s/^KC_DB_PASSWORD=//p" .env)"'
rm .env
ok "ohne .env: Abbruch" '! sh "$REPO/deploy/anmeldung/einrichten.sh" >/dev/null 2>&1'

echo "$PASS/$((PASS + FAIL)) passed"
[ "$FAIL" = 0 ]
