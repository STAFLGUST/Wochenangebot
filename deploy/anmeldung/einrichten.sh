#!/bin/sh
# Zentrale Anmeldung – Schritt 2 der Inbetriebnahme (docs/plattform/inbetriebnahme-anmeldung.md): Geheimnisse erzeugen
# und den Realm-Import vorbereiten. Startet KEINEN Container und ändert nichts am laufenden Betrieb.
#
#   sh deploy/anmeldung/einrichten.sh            # im Installationsordner auf dem Server (dort, wo .env liegt)
#   sh deploy/anmeldung/einrichten.sh --pruefen  # nur anzeigen, was fehlt (keine Änderung)
#
# - Ergänzt in .env nur fehlende Einträge (vorhandene werden nie überschrieben) und zeigt nie einen Wert an.
# - Start-Konto für Keycloak in daten-anmeldung/einrichtung.env (nur bis zur Einrichtung; konten.sh verwaltung löscht es).
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
NAMEN="OIDC_SECRET_DASHBOARD OIDC_SECRET_ANGEBOT OIDC_SECRET_VERWALTUNG OIDC_SECRET_BESTAND OIDC_SECRET_HR OIDC_SECRET_CRM OIDC_SECRET_MARKETING OIDC_CRYPTO_DASHBOARD OIDC_CRYPTO_ANGEBOT OIDC_CRYPTO_VERWALTUNG OIDC_CRYPTO_BESTAND OIDC_CRYPTO_HR OIDC_CRYPTO_CRM OIDC_CRYPTO_MARKETING KC_DB_PASSWORD"
START="$ORDNER/daten-anmeldung/einrichtung.env"   # Start-Konto für Keycloak, nur bis konten.sh verwaltung

[ -f "$ENV" ] || { echo "Abbruch: $ENV nicht gefunden – im Installationsordner ausführen." >&2; exit 1; }
[ -f "$REALM_QUELLE" ] || { echo "Abbruch: $REALM_QUELLE fehlt – Stand von main einspielen." >&2; exit 1; }

hat() { grep -q "^$1=." "$ENV"; }
wert() { sed -n "s/^$1=//p" "$ENV" | tail -1; }
zufall() { od -An -N48 -tx1 /dev/urandom | tr -d ' \n' | cut -c1-48; }

if [ "${1:-}" = "--pruefen" ]; then
  for n in $NAMEN; do
    if hat "$n"; then echo "vorhanden: $n"; else echo "fehlt:     $n"; fi
  done
  if hat KC_VERWALTUNG_PASSWORD; then echo "vorhanden: KC_VERWALTUNG_PASSWORD (Einrichtung abgeschlossen)"
  elif [ -f "$START" ]; then echo "vorhanden: $START (Start-Konto)"; else echo "fehlt:     $START (Start-Konto)"; fi
  if [ -f "$ZIEL" ]; then echo "vorhanden: $ZIEL"; else echo "fehlt:     $ZIEL"; fi
  exit 0
fi

neu=0
[ -n "$(tail -c1 "$ENV")" ] && echo >> "$ENV"
grep -q "^# Zentrale Anmeldung" "$ENV" || printf '%s\n' "# Zentrale Anmeldung (deploy/anmeldung/einrichten.sh) – nie weitergeben" >> "$ENV"
for n in $NAMEN; do
  if ! hat "$n"; then printf '%s=%s\n' "$n" "$(zufall)" >> "$ENV"; neu=$((neu + 1)); echo "erzeugt:   $n"; else echo "vorhanden: $n"; fi
done
chmod 600 "$ENV"
mkdir -p "$ORDNER/daten-anmeldung"; chmod 700 "$ORDNER/daten-anmeldung"
# Start-Konto nur, solange die Einrichtung nicht abgeschlossen ist (kein Verwaltungskonto); ältere Fassungen schrieben es
# in .env – dann von dort übernehmen und aus .env entfernen (Keycloak bekäme sonst leere Werte, wenn sie fehlen)
if ! hat KC_VERWALTUNG_PASSWORD && [ ! -f "$START" ]; then
  if hat KC_BOOTSTRAP_ADMIN_PASSWORD; then
    grep '^KC_BOOTSTRAP_ADMIN_' "$ENV" > "$START.neu"
    grep -q '^KC_BOOTSTRAP_ADMIN_USERNAME=.' "$START.neu" || echo "KC_BOOTSTRAP_ADMIN_USERNAME=einrichtung" >> "$START.neu"
    echo "übernommen: Start-Konto aus .env nach daten-anmeldung/einrichtung.env"
  else
    printf 'KC_BOOTSTRAP_ADMIN_USERNAME=einrichtung\nKC_BOOTSTRAP_ADMIN_PASSWORD=%s\n' "$(zufall)" > "$START.neu"
    echo "erzeugt:   Start-Konto (daten-anmeldung/einrichtung.env)"
  fi
  chmod 600 "$START.neu"; mv "$START.neu" "$START"
fi
if grep -q '^KC_BOOTSTRAP_ADMIN_' "$ENV"; then sed -i '/^KC_BOOTSTRAP_ADMIN_/d' "$ENV"; echo "entfernt:  KC_BOOTSTRAP_ADMIN_* aus .env (gehört nicht dorthin)"; fi

# Realm mit eingesetzten Geheimnissen (Werte enthalten nur 0-9a-f – sicher für sed)
mkdir -p "$ZIEL_DIR"
TMP="$ZIEL.neu"
sed -e "s/@GEHEIM_DASHBOARD@/$(wert OIDC_SECRET_DASHBOARD)/" -e "s/@GEHEIM_ANGEBOT@/$(wert OIDC_SECRET_ANGEBOT)/" \
  -e "s/@GEHEIM_VERWALTUNG@/$(wert OIDC_SECRET_VERWALTUNG)/" -e "s/@GEHEIM_BESTAND@/$(wert OIDC_SECRET_BESTAND)/" \
  -e "s/@GEHEIM_HR@/$(wert OIDC_SECRET_HR)/" -e "s/@GEHEIM_CRM@/$(wert OIDC_SECRET_CRM)/" \
  -e "s/@GEHEIM_MARKETING@/$(wert OIDC_SECRET_MARKETING)/" "$REALM_QUELLE" > "$TMP"
if grep -q "@GEHEIM_" "$TMP"; then rm -f "$TMP"; echo "Abbruch: Platzhalter im Realm nicht ersetzt." >&2; exit 1; fi
mv "$TMP" "$ZIEL"
mkdir -p "$ORDNER/daten-anmeldung/vault"   # Tresor von Keycloak (Dateien, z. B. Postfach-Passwort)
chmod 700 "$ORDNER/daten-anmeldung" "$ZIEL_DIR" "$ORDNER/daten-anmeldung/vault"; chmod 600 "$ZIEL"
if [ "$(id -u)" = 0 ]; then chown -R "$KC_UID" "$ZIEL_DIR" "$ORDNER/daten-anmeldung/vault"; fi
echo "geschrieben: daten-anmeldung/realm-import/realm-mitarbeiter.json"
echo "Fertig ($neu neue Einträge in .env). Nächster Schritt laut Ablaufplan: Keycloak und Datenbank starten (Schritt 3)."
if [ -f "$START" ]; then echo 'Das Start-Konto "einrichtung" steht in daten-anmeldung/einrichtung.env - nur für die Einrichtung (konten.sh verwaltung löscht es).'; fi
