#!/bin/sh
# Zentrale Anmeldung – Schritt 2 der Inbetriebnahme (docs/plattform/inbetriebnahme-anmeldung.md): Geheimnisse erzeugen
# und den Realm-Import vorbereiten. Startet KEINEN Container und ändert nichts am laufenden Betrieb.
#
#   sh deploy/anmeldung/einrichten.sh            # im Installationsordner auf dem Server (dort, wo .env liegt)
#   sh deploy/anmeldung/einrichten.sh --pruefen  # nur anzeigen, was fehlt (keine Änderung)
#
# - Ergänzt in .env nur fehlende Einträge (vorhandene werden nie überschrieben) und zeigt nie einen Wert an.
# - Schreibt daten-anmeldung/realm-import/realm-mitarbeiter.json mit eingesetzten Client-Geheimnissen
#   (nur für den Keycloak-Container lesbar, liegt außerhalb des Repositorys – .gitignore).
# - Mehrfach ausführbar: ein zweiter Lauf ändert nichts mehr.
set -eu
umask 077
ORDNER=$(pwd)
ENV="$ORDNER/.env"
REALM_QUELLE="$ORDNER/deploy/anmeldung/realm-mitarbeiter.json"
ZIEL_DIR="$ORDNER/daten-anmeldung/realm-import"
ZIEL="$ZIEL_DIR/realm-mitarbeiter.json"
KC_UID=${KC_UID:-1000}   # Benutzer im Keycloak-Image (quay.io/keycloak/keycloak)
NAMEN="OIDC_SECRET_DASHBOARD OIDC_SECRET_ANGEBOT OIDC_CRYPTO_DASHBOARD OIDC_CRYPTO_ANGEBOT KC_DB_PASSWORD KC_BOOTSTRAP_ADMIN_PASSWORD"

[ -f "$ENV" ] || { echo "Abbruch: $ENV nicht gefunden – im Installationsordner ausführen." >&2; exit 1; }
[ -f "$REALM_QUELLE" ] || { echo "Abbruch: $REALM_QUELLE fehlt – Stand von main einspielen." >&2; exit 1; }

hat() { grep -q "^$1=." "$ENV"; }
wert() { sed -n "s/^$1=//p" "$ENV" | tail -1; }
zufall() { od -An -N48 -tx1 /dev/urandom | tr -d ' \n' | cut -c1-48; }

if [ "${1:-}" = "--pruefen" ]; then
  for n in $NAMEN KC_BOOTSTRAP_ADMIN_USERNAME; do
    if hat "$n"; then echo "vorhanden: $n"; else echo "fehlt:     $n"; fi
  done
  if [ -f "$ZIEL" ]; then echo "vorhanden: $ZIEL"; else echo "fehlt:     $ZIEL"; fi
  exit 0
fi

neu=0
[ -n "$(tail -c1 "$ENV")" ] && echo >> "$ENV"
grep -q "^# Zentrale Anmeldung" "$ENV" || printf '%s\n' "# Zentrale Anmeldung (deploy/anmeldung/einrichten.sh) – nie weitergeben" >> "$ENV"
for n in $NAMEN; do
  if ! hat "$n"; then printf '%s=%s\n' "$n" "$(zufall)" >> "$ENV"; neu=$((neu + 1)); echo "erzeugt:   $n"; else echo "vorhanden: $n"; fi
done
if ! hat KC_BOOTSTRAP_ADMIN_USERNAME; then echo "KC_BOOTSTRAP_ADMIN_USERNAME=einrichtung" >> "$ENV"; echo "erzeugt:   KC_BOOTSTRAP_ADMIN_USERNAME"; fi
chmod 600 "$ENV"

# Realm mit eingesetzten Geheimnissen (Werte enthalten nur 0-9a-f – sicher für sed)
mkdir -p "$ZIEL_DIR"
TMP="$ZIEL.neu"
sed -e "s/@GEHEIM_DASHBOARD@/$(wert OIDC_SECRET_DASHBOARD)/" -e "s/@GEHEIM_ANGEBOT@/$(wert OIDC_SECRET_ANGEBOT)/" "$REALM_QUELLE" > "$TMP"
if grep -q "@GEHEIM_" "$TMP"; then rm -f "$TMP"; echo "Abbruch: Platzhalter im Realm nicht ersetzt." >&2; exit 1; fi
mv "$TMP" "$ZIEL"
chmod 700 "$ORDNER/daten-anmeldung" "$ZIEL_DIR"; chmod 600 "$ZIEL"
if [ "$(id -u)" = 0 ]; then chown -R "$KC_UID" "$ZIEL_DIR"; fi
echo "geschrieben: daten-anmeldung/realm-import/realm-mitarbeiter.json"
echo "Fertig ($neu neue Einträge in .env). Nächster Schritt laut Ablaufplan: Keycloak und Datenbank starten (Schritt 3)."
echo 'Das Passwort des Start-Kontos "einrichtung" steht in .env (KC_BOOTSTRAP_ADMIN_PASSWORD) - nur für die Einrichtung.'
