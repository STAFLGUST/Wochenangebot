#!/bin/sh
# Test: kcadm wie über „docker compose exec“ – die Ausgabe kommt in kleinen Stücken. Liest der Aufrufer nur den Anfang
# (z. B. „| grep -q“) und schließt die Leitung, scheitert das nächste Stück mit SIGPIPE wie im Betrieb.
# Außerdem wie docker compose exec: die Standardeingabe wird mitgelesen (außer bei „-f -“, dann bekommt kcadm sie) – ein
# Aufruf in „… | while read“ verbrauchte so im Betrieb die restlichen Zeilen der Schleife.
datei=$(mktemp); trap 'rm -f "$datei"' EXIT
case " $* " in
  *" -f - "*) "$@" > "$datei"; rc=$? ;;
  *) [ -t 0 ] || timeout 2 cat > /dev/null; "$@" < /dev/null > "$datei"; rc=$? ;;
esac
groesse=$(wc -c < "$datei"); i=0
while [ "$i" -lt "$groesse" ]; do
  dd if="$datei" bs=128 skip=$((i / 128)) count=1 2>/dev/null || exit 141
  i=$((i + 128)); sleep 0.01
done
exit $rc
