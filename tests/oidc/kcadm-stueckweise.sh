#!/bin/sh
# Test: kcadm wie über „docker compose exec“ – die Ausgabe kommt in kleinen Stücken. Liest der Aufrufer nur den Anfang
# (z. B. „| grep -q“) und schließt die Leitung, scheitert das nächste Stück mit SIGPIPE wie im Betrieb.
datei=$(mktemp); trap 'rm -f "$datei"' EXIT
"$@" > "$datei"; rc=$?
groesse=$(wc -c < "$datei"); i=0
while [ "$i" -lt "$groesse" ]; do
  dd if="$datei" bs=128 skip=$((i / 128)) count=1 2>/dev/null || exit 141
  i=$((i + 128)); sleep 0.01
done
exit $rc
