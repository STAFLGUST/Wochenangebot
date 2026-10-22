## Was ändert sich (für Anwender)
<!-- 2–5 Punkte in Alltagssprache: Wer kann danach was? -->

## Technik / Datenformat
<!-- Betroffene Bereiche, neue Felder/Dokumente (nur erweitern, AGENTS.md Regel 6), Rückfallverhalten -->

## Änderungsfolgen und Koordination
<!-- Ausgabe von: python3 werkzeuge/regeln.py betroffen --basis origin/main
     Bei koordinationspflichtigen Bereichen: was ändert sich an der gemeinsamen Schnittstelle, wer nutzt sie? -->

## Definition of Done (AGENTS.md)
- [ ] Betroffene Testgruppen lokal grün – **Dateien und SQLite** (`python3 werkzeuge/regeln.py betroffen`), volle Suite in der CI grün, beides unten eingetragen
- [ ] Neue Tests für neues Verhalten (inkl. Rechte/Fehlerfälle), `tests/README.md` ergänzt
- [ ] Oberfläche per Bildschirmfoto geprüft (Desktop und Mobil, hell/dunkel bei neuen Farben)
- [ ] `python3 werkzeuge/asset_versionen.py` und `python3 werkzeuge/integritaet.py` grün (Einbindungen ohne `?v=`; Nummern und Prüfliste erzeugt der Server)
- [ ] `python3 werkzeuge/regeln.py pruefen` grün (neue Dateien, Dokumente, Rechte, Testgruppen in `regeln/` eingetragen)
- [ ] Doku aktualisiert (`LIESMICH.md`, ggf. `docs/`), keine Geheimnisse/echten Daten (gitleaks)
- [ ] Keine Produktionsänderung ohne Freigabe; PR als **bereit zum Mergen** markiert (kein Entwurf)

## Tests (tatsächlich ausgeführt)
<!-- z. B. „Dateien 1081/1081, SQLite 1083/1083, Laufzeit 4 min“ -->
