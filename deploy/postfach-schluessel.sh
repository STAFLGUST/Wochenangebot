#!/bin/sh
# Schlüssel des im Eingabebereich hinterlegten Postfach-Passworts aus dem gemeinsamen Datenordner in den Ordner daten-geheim
# umziehen (ADR-007, Postausgang von innen). daten-geheim ist nur in app-mitarbeiter und im Dienst postausgang eingebunden –
# die Kundenseite (app) sieht danach nur noch das verschlüsselte Passwort, nicht den Schlüssel. Wie bisher nicht gesichert.
# Im Installationsordner auf dem Server als root ausführen (dort, wo .env liegt):
#
#   sh deploy/postfach-schluessel.sh status     # wo liegt der Schlüssel?
#   sh deploy/postfach-schluessel.sh umziehen   # daten/mail-schluessel.php → daten-geheim/ (nach dem Release mit dem Postausgang),
#                                               # danach hinterlegte Passwörter an Server und Benutzer binden (Format v2)
#   sh deploy/postfach-schluessel.sh zurueck    # vor einem Rückfall auf ein älteres Release: Passwörter zurück auf Format v1,
#                                               # Schlüssel zurück in den Datenordner (ältere Stände kennen beides nicht anders)
#
# Die Anwendung liest den Schlüssel zuerst aus daten-geheim, sonst aus dem Datenordner (app/api/mail.php) – Umziehen und
# Zurückholen gehen daher ohne Neustart und ohne Unterbrechung. Ohne hinterlegtes Postfach (nur .env) gibt es keinen Schlüssel.
set -eu
umask 077
DATEN="${WA_DATEN:-$(pwd)/daten}"
GEHEIM="${WA_GEHEIM:-$(pwd)/daten-geheim}"
NAME=mail-schluessel.php
EIGNER="${WA_EIGNER:-33:33}"   # www-data im Anwendungs-Image
COMPOSE=${COMPOSE:-docker compose}
BASIS=$(pwd)
# daten/ und daten-geheim sind in den Anwendungs-Containern beschreibbar: ein dort vorab angelegter Verweis darf root nie
# umlenken. Deshalb entsteht die Datei außerhalb beider Ordner (Installationsordner, nur root) und ersetzt den Eintrag dort
# allein per Umbenennen (mv -fT folgt keinem Verweis, es ersetzt ihn – auch einen Verweis auf einen Ordner). Kein Schreiben,
# chown oder chmod auf einen Namen in daten/ oder daten-geheim (gleiche Regel wie status_schreiben() in deploy/sichern.sh).
ablegen() {   # $1 = Quelle (echte Datei), $2 = Zielname im containerbeschreibbaren Ordner
  [ -f "$1" ] && [ ! -L "$1" ] || { echo "Abbruch: $1 ist kein echter Schlüssel (Verweis oder Sonderdatei) – bitte prüfen." >&2; exit 1; }
  TMP=$(mktemp "$BASIS/.mail-schluessel.XXXXXX") || { echo "Abbruch: Zwischendatei nicht anlegbar." >&2; exit 1; }
  cat "$1" > "$TMP" || { rm -f "$TMP"; echo "Abbruch: Schlüssel nicht lesbar." >&2; exit 1; }
  chown "$EIGNER" "$TMP" 2>/dev/null || true
  chmod 600 "$TMP"
  mv -fT "$TMP" "$2" || { rm -f "$TMP"; echo "Abbruch: Schlüssel nicht abgelegt." >&2; exit 1; }
}
# Hinterlegte Passwörter vom Format v1 auf v2 umstellen (an Server und Benutzer gebunden, app/api/mail.php): im Dienst postausgang,
# der den Schlüssel aus daten-geheim liest – danach bringt ein ausgetauschter Server im Datenordner das Passwort nicht mehr heraus
binden() {
  # shellcheck disable=SC2086  # COMPOSE ist bewusst „docker compose“ (zwei Wörter)
  if ! $COMPOSE exec -T postausgang php /var/www/html/api/postausgang.php --umschluesseln; then
    echo "Achtung: Passwörter konnten nicht gebunden werden (läuft der Dienst postausgang?). Später erneut: sh deploy/postfach-schluessel.sh umziehen" >&2
    exit 1
  fi
}
entbinden() {
  # shellcheck disable=SC2086
  if ! $COMPOSE exec -T postausgang php /var/www/html/api/postausgang.php --entbinden; then
    echo "Abbruch: Passwörter konnten nicht auf Format v1 zurückgestellt werden (läuft der Dienst postausgang?) – Schlüssel bleibt in daten-geheim." >&2
    echo "Ohne diesen Schritt muss das Postfach-Passwort nach dem Rückfall im Eingabebereich neu eingegeben werden." >&2
    exit 1
  fi
}
[ -d "$DATEN" ] || { echo "Abbruch: $DATEN nicht gefunden – im Installationsordner ausführen." >&2; exit 1; }
ort() {
  if [ -f "$GEHEIM/$NAME" ]; then echo geheim
  elif [ -f "$DATEN/$NAME" ]; then echo daten
  else echo keiner; fi
}
case "${1:-status}" in
  status)
    case "$(ort)" in
      geheim) echo "Schlüssel des Postfach-Passworts: in daten-geheim (nicht für die Kundenseite lesbar)"
              [ -f "$DATEN/$NAME" ] && echo "  Achtung: zusätzlich noch eine Kopie im Datenordner – sh deploy/postfach-schluessel.sh umziehen entfernt sie." ;;
      daten)  echo "Schlüssel des Postfach-Passworts: noch im gemeinsamen Datenordner – umziehen: sh deploy/postfach-schluessel.sh umziehen" ;;
      *)      echo "Kein Schlüssel vorhanden (kein Postfach-Passwort im Eingabebereich hinterlegt; Zugangsdaten aus .env)." ;;
    esac
    exit 0 ;;
  umziehen)
    mkdir -p "$GEHEIM"
    chown "$EIGNER" "$GEHEIM" 2>/dev/null || true
    chmod 700 "$GEHEIM"
    if [ -f "$DATEN/$NAME" ]; then
      if [ -f "$GEHEIM/$NAME" ]; then
        # beide vorhanden: nur löschen, wenn sie gleich sind – sonst nichts anfassen (welcher gilt, muss ein Mensch entscheiden)
        cmp -s "$DATEN/$NAME" "$GEHEIM/$NAME" || { echo "Abbruch: unterschiedliche Schlüssel in daten/ und daten-geheim/ – bitte prüfen." >&2; exit 1; }
        rm -f "$DATEN/$NAME"
      else
        ablegen "$DATEN/$NAME" "$GEHEIM/$NAME"
        cmp -s "$DATEN/$NAME" "$GEHEIM/$NAME" || { echo "Abbruch: Kopie weicht ab – Datenordner unverändert." >&2; exit 1; }
        rm -f "$DATEN/$NAME"
      fi
      echo "Schlüssel liegt jetzt in daten-geheim; im gemeinsamen Datenordner ist er entfernt."
      binden
    elif [ -f "$GEHEIM/$NAME" ]; then
      echo "Schlüssel liegt bereits in daten-geheim."
      binden
    else
      echo "Nichts umzuziehen: $(sh "$0" status)"
    fi ;;
  zurueck)
    if [ -f "$GEHEIM/$NAME" ] && [ ! -f "$DATEN/$NAME" ]; then
      entbinden
      ablegen "$GEHEIM/$NAME" "$DATEN/$NAME"
      echo "Schlüssel wieder im Datenordner (für ein älteres Release). Die Kopie in daten-geheim bleibt; erneut umziehen mit: sh deploy/postfach-schluessel.sh umziehen"
    else
      echo "Nichts zurückzuholen: $(sh "$0" status)"
    fi ;;
  *) echo "Aufruf: sh deploy/postfach-schluessel.sh status|umziehen|zurueck" >&2; exit 2 ;;
esac
