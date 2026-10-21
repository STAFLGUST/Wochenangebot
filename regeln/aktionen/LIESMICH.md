# Aktionsregister

Jede API-Aktion (`/api/?action=…`) steht in genau einer Datei `regeln/aktionen/<modul>.toml` – der Datei des Moduls,
dem die Aktion fachlich gehört. Daraus erzeugt `python3 werkzeuge/regeln.py erzeugen` die Liste
`app/api/lib/aktionen-liste.php`, nach der der API-Einstieg (`app/api/index.php`) Schreibschutz, öffentlichen Bereich
(IP-/Ländersperre) und Wartungsmodus anwendet. Die CI prüft, dass Code, Register und erzeugte Liste übereinstimmen.

| Feld | Bedeutung | Standard |
| --- | --- | --- |
| `oberflaeche` | Oberfläche aus `regeln/module.toml` (`<modul>.<id>`), auf der die Aktion angeboten wird – Grundlage für „Aktion nur auf ihrem Host“ (GR-109) | Pflicht |
| `schreibend` | `true`: nur per POST mit JSON (CSRF prüft die Aktion selbst) · `"post"`: per GET lesend, per POST schreibend · `false` | `false` |
| `oeffentlich` | ohne Mitarbeiter-Anmeldung erreichbar (Angebotsseite, Kundenportal); nur auf externen Oberflächen | `false` |
| `kunden_wartung` | pausiert im Wartungsmodus der Angebotsseite (503), nur für öffentliche Aktionen (GR-009) | `false` |

Neue Aktion: Eintrag in der Datei des eigenen Moduls, `python3 werkzeuge/regeln.py erzeugen`, danach
`python3 werkzeuge/integritaet.py --setzen`. Die Berechtigung prüft weiterhin die Aktion selbst (`require_perm`, GR-103) –
das Register ersetzt keine Rechteprüfung. Konflikt in `aktionen-liste.php` nach einem Rebase: nicht von Hand
zusammenführen, sondern neu erzeugen.
