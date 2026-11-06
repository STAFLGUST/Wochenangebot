#!/bin/sh
# Test von deploy/cdn-netzsperre.sh (Netzsperre für bunny.net) – mit Platzhaltern für nft, systemctl, ip, journalctl und curl,
# Liste aus Dateien mit Dokumentationsadressen (WA_TESTNETZE=1), in einem Wegwerf-Ordner. Das echte Regelwerk prüft
# tests/deploy/test_cdn_netzsperre.py mit nftables.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS + 1)); echo "PASS $1"; else FAIL=$((FAIL + 1)); echo "FAIL $1"; echo "$AUS" | sed 's/^/    /'; fi; }
mkdir -p "$T/bin" "$T/units" "$T/inst"
# nft: Tabelle als Datei; -f übernimmt (außer mit $T/nft-fehler), list zeigt sie mit Zählern, delete entfernt sie
cat > "$T/bin/nft" <<EOF
#!/bin/sh
echo "nft \$*" >> "$T/aufrufe"
case "\$1" in
  -f) [ ! -e "$T/nft-fehler" ] || exit 1; cp "\$2" "$T/tabelle" ;;
  list) [ -e "$T/tabelle" ] || exit 1; sed 's/counter jump/counter packets 7 bytes 420 jump/' "$T/tabelle" ;;
  delete) rm -f "$T/tabelle" ;;
esac
EOF
printf '#!/bin/sh\necho "systemctl $*" >> "%s/aufrufe"\n[ "$1" != is-active ] || echo active\n' "$T" > "$T/bin/systemctl"
printf '#!/bin/sh\n[ -e "%s/keine-route" ] || echo "default via 192.0.2.254 dev eth0 proto static"\n' "$T" > "$T/bin/ip"
printf '#!/bin/sh\nfor i in 1 2 3; do echo "stafl-netzsperre: IN=eth0 OUT= SRC=198.51.100.77 DST=192.0.2.1 PROTO=TCP SPT=4 DPT=443"; done\necho "andere Meldung"\n' > "$T/bin/journalctl"
printf '#!/bin/sh\necho "curl $*" >> "%s/aufrufe"\n[ ! -e "%s/curl-fehler" ]\n' "$T" "$T" > "$T/bin/curl"
chmod +x "$T/bin/"*
python3 -c 'import json; n=["192.0.2.","198.51.100.","203.0.113."]; print(json.dumps([n[i//256]+str(i%256) for i in range(300)]))' > "$T/v4.json"
echo '["2001:db8::7"]' > "$T/v6.json"
export WA_NFT="$T/bin/nft" WA_SYSTEMCTL="$T/bin/systemctl" WA_IP="$T/bin/ip" WA_JOURNAL="$T/bin/journalctl" WA_CURL="$T/bin/curl" \
  WA_UNITS="$T/units" WA_PAUSE=0 WA_OHNE_ROOT=1 WA_TESTNETZE=1 WA_BUNNY_V4="file://$T/v4.json" WA_BUNNY_V6="file://$T/v6.json" AUS CODE VORHER
mkdir -p "$T/inst/deploy" && cp "$REPO/deploy/cdn-netzsperre.sh" "$REPO/deploy/cdn_netzsperre.py" "$T/inst/deploy/"
cd "$T/inst"
S="sh deploy/cdn-netzsperre.sh"
f_aufrufe() { grep -c "^nft -f" "$T/aufrufe" 2>/dev/null || true; }

AUS=$($S status 2>&1) && CODE=0 || CODE=$?
ok "status ohne Einrichtung: aus, keine Regeln" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Netzsperre: aus" && echo "$AUS" | grep -q "Regeln gesetzt: nein"'
AUS=$($S beobachten 2>&1) && CODE=0 || CODE=$?
ok "beobachten ohne .env: Abbruch mit Hinweis" '[ $CODE = 1 ] && echo "$AUS" | grep -q "Installationsordner"'
printf 'DOMAIN=angebot-stafl.de\nCDN_SCHLUESSEL=0123456789abcdef0123456789abcdef\nCDN_PFLICHT=0\n' > .env
AUS=$($S beobachten 2>&1) && CODE=0 || CODE=$?
ok "ohne CDN_PFLICHT=1: Abbruch, nichts gesetzt, kein Timer" '[ $CODE = 1 ] && echo "$AUS" | grep -q "CDN_PFLICHT=1" && [ ! -e "$T/tabelle" ] && [ -z "$(ls "$T/units")" ]'
printf 'DOMAIN=angebot-stafl.de\nCDN_SCHLUESSEL=kurz\nCDN_PFLICHT=1\n' > .env
AUS=$($S beobachten 2>&1) && CODE=0 || CODE=$?
ok "zu kurzer Schlüssel: Abbruch" '[ $CODE = 1 ] && [ ! -e "$T/tabelle" ]'
printf 'DOMAIN=angebot-stafl.de\nCDN_SCHLUESSEL=0123456789abcdef0123456789abcdef\nCDN_PFLICHT=1\n' > .env
mv "$T/v4.json" "$T/v4.weg"
AUS=$($S beobachten 2>&1) && CODE=0 || CODE=$?
ok "bunny-Liste nicht abrufbar und keine vorhanden: Abbruch, kein Timer, keine Regeln" '[ $CODE = 1 ] && echo "$AUS" | grep -q "ohne bunny-Liste" && [ -z "$(ls "$T/units")" ] && [ ! -e "$T/tabelle" ] && [ ! -e .cdn-netzsperre ]'
mv "$T/v4.weg" "$T/v4.json"

AUS=$($S beobachten 2>&1) && CODE=0 || CODE=$?
ok "beobachten: Regeln ohne drop, Modus gespeichert" '[ $CODE = 0 ] && [ -e "$T/tabelle" ] && ! grep -q "^[[:space:]]*drop" "$T/tabelle" && [ "$(cat .cdn-netzsperre)" = beobachten ] && echo "$AUS" | grep -q "Nichts wird verworfen"'
ok "nur die Schnittstelle der Standardroute" 'grep -q "iifname \"eth0\"" "$T/tabelle"'
ok "Timer eingerichtet: Installationsordner, alle 30 Minuten, aktiviert" 'grep -q "WorkingDirectory=$T/inst" "$T/units/wochenangebot-netzsperre.service" && grep -q "ExecStart=/bin/sh $T/inst/deploy/cdn-netzsperre.sh aktualisieren" "$T/units/wochenangebot-netzsperre.service" && grep -q "OnUnitActiveSec=30min" "$T/units/wochenangebot-netzsperre.timer" && grep -q "systemctl enable --now wochenangebot-netzsperre.timer" "$T/aufrufe"'
ok "Liste und Stand nur für den Besitzer lesbar" '[ "$(stat -c %a .cdn-netzsperre-liste.json)" = 600 ] && [ "$(stat -c %a .cdn-netzsperre)" = 600 ] && [ "$(stat -c %a .cdn-netzsperre-regeln)" = 600 ]'
AUS=$($S status 2>&1) && CODE=0 || CODE=$?
ok "status: Modus, Zähler, Timer, fremde Adressen aus dem Kernel-Protokoll" '[ $CODE = 0 ] && echo "$AUS" | grep -q "Netzsperre: beobachten" && echo "$AUS" | grep -q "Gezählte fremde Verbindungen seit dem Setzen: 28" && echo "$AUS" | grep -q "Timer: active" && echo "$AUS" | grep -q "198.51.100.77" && echo "$AUS" | grep -q "300 IPv4, 1 IPv6"'
VORHER=$(f_aufrufe)
AUS=$($S aktualisieren 2>&1) && CODE=0 || CODE=$?
ok "aktualisieren ohne Änderung: Regeln nicht neu gesetzt (Zähler bleiben)" '[ $CODE = 0 ] && [ "$(f_aufrufe)" = "$VORHER" ]'

AUS=$($S an 2>&1) && CODE=0 || CODE=$?
ok "an: verwirft, Probe über bunny an die eigene Domain" '[ $CODE = 0 ] && grep -q "^[[:space:]]*drop" "$T/tabelle" && [ "$(cat .cdn-netzsperre)" = an ] && grep -q "curl .*https://angebot-stafl.de/api/?action=status" "$T/aufrufe" && echo "$AUS" | grep -q "Probe über bunny erfolgreich"'
AUS=$($S status 2>&1)
ok "status im Modus an: verworfene Verbindungen" 'echo "$AUS" | grep -q "Netzsperre: an" && echo "$AUS" | grep -q "Verworfene fremde Verbindungen"'
touch "$T/curl-fehler"
AUS=$($S an 2>&1) && CODE=0 || CODE=$?
ok "an mit gescheiterter Probe: zurück auf beobachten, nichts verworfen" '[ $CODE = 1 ] && [ "$(cat .cdn-netzsperre)" = beobachten ] && ! grep -q "^[[:space:]]*drop" "$T/tabelle" && echo "$AUS" | grep -q "zurück auf Modus beobachten" && [ "$(grep -c "^curl " "$T/aufrufe")" -ge 4 ]'
rm -f "$T/curl-fehler"
$S an >/dev/null 2>&1

# Timer: alte Liste und kaputte Quelle → bisherige Liste und Regeln bleiben
python3 - <<'EOF'
import json
d = json.load(open(".cdn-netzsperre-liste.json")); d["abgerufen"] = "2026-01-01T00:00:00Z"
json.dump(d, open(".cdn-netzsperre-liste.json", "w"))
EOF
echo "<html>" > "$T/v4.json"
VORHER=$(f_aufrufe)
AUS=$($S aktualisieren 2>&1) && CODE=0 || CODE=$?
ok "aktualisieren mit kaputter bunny-Antwort: bisherige Liste und Regeln bleiben" '[ $CODE = 0 ] && echo "$AUS" | grep -q "bisherige bleibt" && grep -q "^[[:space:]]*drop" "$T/tabelle" && [ "$(f_aufrufe)" = "$VORHER" ]'
touch "$T/keine-route"
AUS=$($S aktualisieren 2>&1) && CODE=0 || CODE=$?
ok "ohne Standardroute: Fehler, Regeln unverändert" '[ $CODE = 1 ] && grep -q "^[[:space:]]*drop" "$T/tabelle"'
rm -f "$T/keine-route"
rm -f .cdn-netzsperre-regeln; touch "$T/nft-fehler"
AUS=$($S aktualisieren 2>&1) && CODE=0 || CODE=$?
ok "nft lehnt ab: Fehler, bisheriger Stand bleibt" '[ $CODE = 1 ] && echo "$AUS" | grep -q "bisheriger Stand bleibt" && grep -q "^[[:space:]]*drop" "$T/tabelle"'
rm -f "$T/nft-fehler"

mv .env env.weg
AUS=$($S aus 2>&1) && CODE=0 || CODE=$?
ok "aus (auch ohne .env): Regeln, Timer und Modus entfernt" '[ $CODE = 0 ] && [ ! -e "$T/tabelle" ] && [ ! -e .cdn-netzsperre ] && [ -z "$(ls "$T/units")" ] && grep -q "systemctl disable --now wochenangebot-netzsperre.timer" "$T/aufrufe" && echo "$AUS" | grep -q "wieder Verbindungen von überall"'
VORHER=$(f_aufrufe)
AUS=$($S aktualisieren 2>&1) && CODE=0 || CODE=$?
ok "aktualisieren nach aus: nichts gesetzt" '[ $CODE = 0 ] && [ ! -e "$T/tabelle" ] && [ "$(f_aufrufe)" = "$VORHER" ]'
AUS=$($S vielleicht 2>&1) && CODE=0 || CODE=$?
ok "unbekannter Befehl abgelehnt" '[ $CODE = 2 ]'
if [ "$(id -u)" != 0 ]; then
  AUS=$(WA_OHNE_ROOT='' $S status 2>&1) && CODE=0 || CODE=$?
  ok "ohne root: Abbruch" '[ $CODE = 1 ] && echo "$AUS" | grep -q "als root"'
fi
echo "cdn-netzsperre.sh: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
