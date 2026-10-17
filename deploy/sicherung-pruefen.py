"""Prüft eine entpackte Datensicherung: jede Datendatei muss gültiges JSON enthalten. Gibt die Anzahl fehlerhafter Dateien aus."""
import json, os, sys

GUARD = "<?php http_response_code(404); exit; ?>\n"
bad = 0
for root, _, files in os.walk(sys.argv[1]):
    for name in files:
        if not name.endswith('.php') or name == 'index.php':
            continue
        try:
            with open(os.path.join(root, name), encoding='utf-8') as fh:
                text = fh.read()
            if text.startswith(GUARD):
                text = text[len(GUARD):]
            json.loads(text)
        except Exception:
            bad += 1
print(bad)
