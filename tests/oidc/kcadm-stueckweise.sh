#!/bin/sh
# Test: kcadm wie über „docker compose exec“ – die Ausgabe kommt in Stücken. Liest der Aufrufer nur den Anfang
# (z. B. „| grep -q“) und schließt die Leitung, scheitert das zweite Stück mit SIGPIPE wie im Betrieb.
aus=$("$@"); rc=$?
printf '%s' "$aus" | head -c 64
sleep 0.3
printf '%s\n' "$aus" | tail -c +65 || exit 141
exit $rc
