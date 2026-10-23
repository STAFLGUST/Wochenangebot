# Schnittstelle: Importverträge und Importzentrale

Stand: Roadmap 10b. Die Importzentrale (Eingabebereich → Verwaltung → „Import“, Ziel-Oberfläche `verwaltung.import`) bündelt
alle Importe mit einem Ablauf: **Importart wählen → Datei wählen → Vorschau → übernehmen → Ergebnis und Protokoll.**

Grundsatz: **Importleser bleiben beim Daten-Eigentümer** (`regeln/datenverantwortung.toml`, GR-101). Die Zentrale liest
keine Dateiformate und greift auf keine Daten zu; sie ruft nur die Funktionen des Eigentümers auf (der Test
`importzentrale` prüft, dass die Zentrale weder `store_*` noch `with_lock` verwendet).

## Bestand der Importe (Oktober 2026)

| Importart (`id`) | Datei | Leser (Browser) | Prüfung/Speichern (Server) | Recht | Eigentümer | Bisherige Stelle (bleibt) |
| --- | --- | --- | --- | --- | --- | --- |
| `kunden` | CSV Kundendaten-Export | `kAusCsv` (admin-verwaltung.js) | `kunden_import_lauf` | `kunden.bearbeiten` + Passwortbestätigung `kunden_import` | verwaltung | Stammdaten → Kunden, Aktion `kunden_import` |
| `kundengruppen`, `vkgruppen`, `vertreter` | CSV Listen | `gruppenListe().ausCsv` (admin-verwaltung.js) | `gruppen_speichern` | `stammdaten.bearbeiten` | verwaltung | Stammdaten → …, Aktionen `*_save` |
| `stammdaten` | CSV Artikelstammdaten-Export | `masterAusCsv` + `masterZusammenfuehren` (admin.js) | `stammdaten_speichern` | `stammdaten.bearbeiten` | verwaltung | Stammdaten → Artikelstammdaten, Aktion `master_save` |
| `bestand` | WinAB-Bestandsliste .xls/.xlsx | `StockCore` (stock-core.js) über `stockAusDatei` (admin.js) | `bestand_speichern` | `bestand.importieren` | bestand | Bestand, Aktion `stock_import` |
| `preisverlauf` | Angebotslisten .xlsx (mehrere) | `OfferCore.parseOfferWorkbook` über `histAusDatei` (admin.js) | `preisverlauf_woche_speichern` | `preisverlauf.bearbeiten` | angebot | Preisverlauf → Daten, Aktion `history_import` |
| `angebot_excel` | Wochenangebot .xlsx | Angebotsleser (offer-core.js) | Entwurf (`save_draft`) | `angebot.bearbeiten` | angebot | Angebotseditor „Excel importieren“ – Ablauf `editor` |
| `urlaubsplanung` | Excel-Urlaubsplanung (ein Blatt je Monat) | `importLeser.urlaubsplanung` (app/module/hr/verwaltung-hr.js, OfferCore-Excel-Leser) | `hr_import_vorschau`/`hr_import_uebernehmen` (unbekannte Namen → Mitarbeiter ohne Anmeldung über `mitarbeiter_ohne_zugang_anlegen`) | `hr.verwalten` | hr | – (bis Oktober 2026 im HR-Bereich „Mitarbeiter“) |
| `angebot_preise` | CSV Artikelpreise | `preiseAusCsv` (admin.js) | Entwurf (`save_draft`) | `angebot.bearbeiten`, `angebote.verwalten` | angebot | Stammdaten → Angebote „Preise importieren“ – Ablauf `editor` |

Nicht aufgenommen: Import der Schutz-Einstellungen (`fw_import`, Plattformkern, nur Administratoren) – das ist eine
Konfigurationsdatei dieser Anwendung, kein Datenimport aus einem Fremdsystem; er bleibt in der Schutzzentrale.

Ablauf `editor`: Wochenangebot und Artikelpreise ändern den **Entwurf**; Vorschau, Abgleich mit dem Stand anderer
Bearbeiter, „Rückgängig“ und Veröffentlichen gibt es nur im Angebotseditor. Die Zentrale führt sie auf (Rechte wie dort)
und öffnet den Editor – es gibt keinen zweiten Weg, der den Entwurf ersetzt.

## Vertrag des Eigentümers (Server)

Datei `app/api/module/<modul>/import.php`, geladen von `app/api/index.php`, Modul in `IMPORT_EIGENTUEMER`
(`app/api/module/verwaltung/importzentrale.php`). Funktion `import_arten_<modul>(): array` liefert je Importart:

| Feld | Pflicht | Bedeutung |
| --- | --- | --- |
| `name`, `beschreibung` | ja | Anzeige |
| `recht` | ja | Liste der Rechte (alle nötig, GR-103); die Zentrale zeigt die Art nur Berechtigten und prüft serverseitig (403) |
| `aktion` | ja | registrierte Importaktion des Eigentümers (`regeln/aktionen/<modul>.toml`); deren Oberfläche entscheidet über Wartung (GR-107, 503) |
| `dateien`, `kodierung` | ja | erlaubte Endungen (`csv`, `xls`, `xlsx`, `xlsm`) und Text für die Anzeige |
| `vorschau`, `uebernahme` | bei Ablauf `zentrale` | Funktionsnamen `f(array $eingabe, array $nutzer): array` |
| `ablauf` | nein | `zentrale` (Standard) oder `editor` |
| `optionen` | nein | `[{id, typ: schalter|datum, label, standard?, pflicht?}]` – die Zentrale übergibt nur diese, mit Standardwert |
| `mehrere`, `bestaetigung`, `ansicht` | nein | mehrere Dateien; Schlüssel der Passwortbestätigung (Katalog `BESTAETIGUNG`); Ansicht für „… öffnen“ |

`$eingabe` = vom Leser gelieferte `daten` plus `art`, `quelle` (Dateiname), `optionen`, `stand`. Rückgabe von Vorschau
und Übernahme (gleiche Form):

```text
zahlen   { neu, geaendert, entfaellt, unveraendert, fehler }   – zählen immer alle Zeilen
zeilen   [{ art: neu|geaendert|entfaellt|fehler, zeile?, schluessel, name, text }]   – die Zentrale sendet höchstens 500
hinweise [{ stufe: info|warn, text }]
stand    Revision/Kennung des gespeicherten Stands
```

Die Übernahme bekommt `stand` aus der Vorschau zurück und weist mit **409** ab, wenn sich die Daten inzwischen geändert
haben. Sie schreibt das **Protokoll** (gleiche Einträge wie die bisherige Aktion). Die bisherigen Aktionen rufen dieselben
Speicherfunktionen auf – je Importart gibt es genau eine Prüf- und Speicherlogik.

## Vertrag des Lesers (Browser)

`window.WA.importLeser[<id>] = { lesen(dateien) → { daten, zeilen, fehler: [{zeile?, schluessel?, datei?, text}], hinweise, optionen? }, nachher() }`
– registriert in der Datei, in der der Leser heute schon für den Import an Ort und Stelle läuft (admin.js,
admin-verwaltung.js). Wirft der Leser, ist die Datei unlesbar oder falsch (Meldung wird angezeigt, nichts übernommen).
Vor dem Leser prüft die Zentrale einheitlich Endung, leere Datei, Größe (30 MB), Excel statt CSV, UTF-16 statt
UTF-8/Windows-1252 und Excel-Kennung.

## Aktionen der Zentrale

| Aktion | Art | Inhalt |
| --- | --- | --- |
| `import_arten` | GET | Importarten des Nutzers (nur mit Recht), mit Wartungszustand |
| `import_pruefen` | POST | `{ art, daten, quelle, optionen }` → Vorschau |
| `import_uebernehmen` | POST | wie oben plus `stand` → Übernahme (ggf. Passwortbestätigung) |

Heute auf der Oberfläche `angebot.eingabe` registriert (`regeln/aktionen/verwaltung.toml`); mit der Freigabe von
`verwaltung.import` ziehen sie dorthin um.

**Neue Importart:** Eintrag in `import_arten_<modul>()` des Eigentümers, Vorschau-/Übernahmefunktion dort, Leser in
`window.WA.importLeser` und – falls ein neues Recht – in `RECHTE` von `admin-import.js` (nur Anzeige des Menüpunkts);
Test in der Gruppe des Eigentümers und in `importzentrale`.
