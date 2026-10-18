## Was ändert sich (für Anwender)
<!-- 2–5 Punkte in Alltagssprache: Wer kann danach was? -->

## Technik / Datenformat
<!-- Betroffene Bereiche, neue Felder/Dokumente (nur erweitern, AGENTS.md Regel 6), Rückfallverhalten -->

## Definition of Done (AGENTS.md)
- [ ] Volle E2E-Suite lokal grün – **Dateien und SQLite** (`python3 tests/run_e2e.py`, `WA_TEST_STORAGE=sqlite …`), Ergebnis unten eingetragen
- [ ] Neue Tests für neues Verhalten (inkl. Rechte/Fehlerfälle), `tests/README.md` ergänzt
- [ ] Oberfläche per Bildschirmfoto geprüft (Desktop und Mobil, hell/dunkel bei neuen Farben)
- [ ] `python3 werkzeuge/asset_versionen.py` grün (nach Änderungen an `app/assets/`: `--setzen`)
- [ ] Doku aktualisiert (`LIESMICH.md`, ggf. `docs/`), keine Geheimnisse/echten Daten (gitleaks)
- [ ] Keine Produktionsänderung ohne Freigabe; PR als **bereit zum Mergen** markiert (kein Entwurf)

## Tests (tatsächlich ausgeführt)
<!-- z. B. „Dateien 1081/1081, SQLite 1083/1083, Laufzeit 4 min“ -->
