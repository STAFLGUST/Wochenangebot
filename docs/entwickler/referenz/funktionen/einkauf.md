# Funktionen: Einkauf (`einkauf`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

2 Dateien, 6 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/lib/einkauf.php`

_Einkauf: Fehlmengen aus offenen Bestellwünschen gegenüber der zuletzt übernommenen Bestandsliste._

- `einkauf_bedarf(mitKunden)` – $mitKunden: Firmennamen der Bestellwünsche (nur Bearbeiter/Administrator)
- `einkauf_mail(items, stock, note, by)` – E-Mail an den Einkauf: [Betreff, Text, HTML]

## `tests/e2e/test_einkauf.py`

_Einkauf: Fehlmengen aus offenen Bestellwünschen gegenüber dem Bestand, Rechte je Rolle (Ansehen für alle, Kundennamen und Melden ab Bearbeiter), E-Mail an die Empfänger „Einkaufsbedarf“, Status „gemeldet“, Oberfläche._

- `check(n, c, i)`
- `customer(username, firma)`
- `order(k, pos, termin, ref)`

**ohne Bestandsliste**

**Bestand übernehmen**

**stornierte / erledigte zählen nicht**

**Benachrichtigen**

**Oberfläche**

- `login(user, password, w, h)`
