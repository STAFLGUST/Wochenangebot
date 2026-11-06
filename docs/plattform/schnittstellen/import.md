# Schnittstelle: Importverträge und Importzentrale

Stand: Roadmap 10b. Die Importzentrale (Eingabebereich → Verwaltung → „Import“, Ziel-Oberfläche `verwaltung.import`) bündelt
alle Importe mit einem Ablauf: **Importart wählen → Datei wählen → Vorschau → übernehmen → Ergebnis und Protokoll.**

Grundsatz: **Importleser bleiben beim Daten-Eigentümer** (`regeln/datenverantwortung.toml`, GR-101). Die Zentrale liest
keine Dateiformate und greift auf keine Daten zu; sie ruft nur die Funktionen des Eigentümers auf (der Test
`importzentrale` prüft, dass die Zentrale weder `store_*` noch `with_lock` verwendet).

## Bestand der Importe (Oktober 2026)

| Importart (`id`) | Datei | Leser (Browser) | Prüfung/Speichern (Server) | Recht | Eigentümer | Bisherige Stelle (bleibt) |
| --- | --- | --- | --- | --- | --- | --- |
| `kunden` | CSV Kundendaten-Export (alle Spalten; weitere als `wawi`, `wawiFelder`) | `kAusCsv` (admin-verwaltung.js) | `kunden_import_lauf` (Optionen `ohneStern`, `anlegen`, `aktivRegel` – 18 Monate ohne Rechnung → inaktiv) | `kunden.bearbeiten` + Passwortbestätigung `kunden_import` | verwaltung | Stammdaten → Kunden, Aktion `kunden_import` |
| `kundengruppen`, `vkgruppen`, `vertreter`, `versandarten`, `lieferanten` | CSV Listen | `gruppenListe().ausCsv` (admin-verwaltung.js) | `gruppen_speichern` | `stammdaten.bearbeiten` | verwaltung | Stammdaten → …, Aktionen `*_save` |
| `stammdaten` | CSV Artikelstammdaten-Export | `masterAusCsv` + `masterZusammenfuehren` (admin.js) | `stammdaten_speichern` | `stammdaten.bearbeiten` | verwaltung | Stammdaten → Artikelstammdaten, Aktion `master_save` |
| `bestand` | WinAB-Bestandsliste als CSV (Semikolon, Windows-1252/UTF-8) oder .xls/.xlsx | `StockCore` (stock-core.js) über `stockAusDatei` (admin.js) | `bestand_speichern` | `bestand.importieren` | bestand | Bestand, Aktion `stock_import` |
| `preisverlauf` | Angebotslisten .xlsx (mehrere) | `OfferCore.parseOfferWorkbook` über `histAusDatei` (admin.js) | `preisverlauf_woche_speichern` | `preisverlauf.bearbeiten` | angebot | Preisverlauf → Daten, Aktion `history_import` |
| `zeiterfassung` | Abwesenheitsbericht der Zeiterfassung (.xlsx, Importvorlage für Urlaub und Krankheit) | `importLeser.zeiterfassung` (app/module/hr/verwaltung-hr.js, erstes Blatt) | `hr_zeit_vorschau`/`hr_zeit_uebernehmen` (Personalnummer, sonst Name; Option `abteilungen`; ersetzt frühere Übernahme im Zeitraum) | `hr.verwalten` | hr | – |
| `angebot_preise` | CSV Artikelpreise der Warenwirtschaft (Preis-Art; Kundengruppe; Artikel; Preis) | `preiseAusCsv` (admin.js, Leser `angebot_preise`) | `angebot_preise_vorschau` / `_uebernehmen` (module/angebot/import.php): ohne Kundengruppe ins Wochenangebot, mit Kundengruppe ins Angebot der Gruppe, in den **Entwurf** (Sperre `entwurf`, Stand = Revision Entwurf und Angebotsliste, 409); Option `woche` (Auswahl, Standard aktuelle KW) setzt die Angebotswoche, Option `gruppen` (Liste, Standard leer) nennt die Kundengruppen ohne Angebot, für die je ein Angebot angelegt wird; eigene Darstellung `importDarstellung.angebot_preise` (app/module/angebot/preisimport.js: bisher → neu je Angebot, „Bitte prüfen“ ab 10 %, Gruppen einzeln anhaken) | `angebot.bearbeiten`, `angebote.verwalten` | angebot | – (seit 04.11.2026 nur hier; vorher Stammdaten → Angebote) |
| `umsatzdaten` | CSV Kundenumsatztabelle der Warenwirtschaft (Kunde, Datum, Artikel, Kolli, Menge, Preis, Gesamtbetrag, EKPreis; bis 200 MB) | `importLeser.umsatzdaten` (app/module/controlling/umsatz-import.js): je Kunde, Artikel und Tag zusammengefasst, je Monat ein Teil mit Prüfsumme | `umsatzdaten_import_vorschau` / `_teil` / `_uebernehmen` (module/controlling/umsatzdaten.php): Zeitraum der Datei ersetzt den gespeicherten Zeitraum, nur geänderte Monate werden übertragen | `controlling.umsatz_importieren` | controlling | – (neu, November 2026) |
| `zeitbericht` | Zeitbericht der Zeiterfassung (.xlsx; Vorname, Nachname, Datum, Hinein, Hinaus, Geplant, Gearbeitete Stunden, Saldo, optional Abwesenheit, Pause, Mitarbeiternummer, Department) | `importLeser.zeitbericht` (app/module/controlling/arbeitszeit-import.js, erstes Blatt als Raster) | `arbeitszeit_import_vorschau` / `_uebernehmen` (module/controlling/arbeitszeit.php): Zeitraum der Datei ersetzt die gespeicherten Tage, Stempelfehler markiert, nie geschätzt | `controlling.arbeitszeit_importieren` | controlling | – (neu, November 2026) |

Nicht aufgenommen: Import der Schutz-Einstellungen (`fw_import`, Plattformkern, nur Administratoren) – das ist eine
Konfigurationsdatei dieser Anwendung, kein Datenimport aus einem Fremdsystem; er bleibt in der Schutzzentrale.

Ablauf `editor` (Importart nur aufgeführt, die Zentrale öffnet die Ansicht `ansicht`): wird derzeit von keiner Importart
genutzt. Der Excel-Import des Wochenangebots im Angebotseditor ist am 04.11.2026 entfallen; die Artikelpreise laufen seitdem
in der Zentrale und schreiben in den Entwurf – offene Angebotseditoren übernehmen die Änderung über den Abgleich
(`draft_ping`/`mergeModels`), veröffentlicht wird weiter nur im Editor.

## Vertrag des Eigentümers (Server)

Datei `app/api/module/<modul>/import.php`, geladen von `app/api/index.php`, Modul in `IMPORT_EIGENTUEMER`
(`app/api/module/verwaltung/importzentrale.php`). Funktion `import_arten_<modul>(): array` liefert je Importart:

| Feld | Pflicht | Bedeutung |
| --- | --- | --- |
| `name`, `beschreibung` | ja | Anzeige (die ausführliche Beschreibung als Hinweis beim Darüberfahren) |
| `kurz` | nein | eine Zeile für die Liste der Zentrale (bis etwa 45 Zeichen, höchstens 60); fehlt sie, steht dort die Beschreibung |
| `recht` | ja | Liste der Rechte (alle nötig, GR-103); die Zentrale zeigt die Art nur Berechtigten und prüft serverseitig (403) |
| `aktion` | ja | registrierte Importaktion des Eigentümers (`regeln/aktionen/<modul>.toml`); deren Oberfläche entscheidet über Wartung (GR-107, 503) |
| `dateien`, `kodierung` | ja | erlaubte Endungen (`csv`, `xls`, `xlsx`, `xlsm`) und Text für die Anzeige |
| `vorschau`, `uebernahme` | bei Ablauf `zentrale` | Funktionsnamen `f(array $eingabe, array $nutzer): array` |
| `ablauf` | nein | `zentrale` (Standard) oder `editor` |
| `optionen` | nein | `[{id, typ: schalter|datum|auswahl|liste, label, standard?, pflicht?, werte?}]` – die Zentrale übergibt nur diese, mit Standardwert; `auswahl`: feste Werte `werte: [{wert, text}]`, `standard` muss einer davon sein, andere Werte ersetzt der Server durch den Standard; `liste`: Kennungen (`[A-Za-z0-9._-]{1,40}`, ohne Doppelte, höchstens 500, `standard` eine solche Liste) – die einheitliche Oberfläche zeigt dafür kein Feld, gesetzt wird sie von der eigenen Darstellung des Eigentümers; ob die Kennungen passen, prüft der Eigentümer |
| `mehrere`, `bestaetigung`, `ansicht` | nein | mehrere Dateien; Schlüssel der Passwortbestätigung (Katalog `BESTAETIGUNG`); Ansicht für „… öffnen“ |
| `teile` | nein | große Datei in Teilen: Funktionsname `f(array $eingabe, array $nutzer): void` für einen Teil (Zwischenablage des Eigentümers); nur Ablauf `zentrale` |
| `maxMb` | nein | Größe einer Datei in MB (Prüfung im Browser): Standard 30, mit `teile` bis 200 |

`$eingabe` = vom Leser gelieferte `daten` plus `art`, `quelle` (Dateiname), `optionen`, `stand`. Rückgabe von Vorschau
und Übernahme (gleiche Form):

```text
zahlen   { neu, geaendert, entfaellt, unveraendert, fehler }   – zählen immer alle Zeilen
zeilen   [{ art: neu|geaendert|entfaellt|fehler, zeile?, schluessel, name, text }]   – die Zentrale sendet höchstens 500
hinweise [{ stufe: info|warn, text }]
stand    Revision/Kennung des gespeicherten Stands
details  (nein) beliebige Daten nur für die eigene Darstellung des Eigentümers im Browser – die Zentrale wertet sie nicht aus,
         reicht sie nur bis 3 MB (JSON) durch, sonst entfallen sie und der Browser zeigt die einheitliche Vorschau
fuss     (nein) Zusammenfassung über dem Knopf, z. B. „3 Preise in 3 Angeboten · keine neuen Angebote“ (höchstens 300 Zeichen)
knopf    (nein) Beschriftung des Knopfs, z. B. „3 Preise übernehmen“ (höchstens 60 Zeichen)
```

`details` dienen nur der Anzeige: Was übernommen wird, ermittelt die Übernahme des Eigentümers erneut aus Datei und
Optionen (GR-103); `zahlen`, `zeilen` und `hinweise` müssen weiterhin vollständig sein (einheitliche Vorschau als Rückfall).

Zusätzlich bei Importarten mit `teile`: die Vorschau liefert `teile` = Liste der Kennungen (höchstens 2000, `[A-Za-z0-9_-]{1,40}`),
die der Eigentümer für die Übernahme braucht (z. B. nur geänderte Monate), und `$eingabe` enthält `upload` (Kennung des Importlaufs,
32 Hex-Zeichen, vom Browser zufällig gewählt). Vor der Übernahme schickt der Browser jeden verlangten Teil einzeln mit `import_teil`
(`$eingabe` = `art`, `upload`, `schluessel`, `daten`, `quelle`; je Anfrage höchstens 6 MB); der Eigentümer prüft ihn und legt ihn
unter Kennung und Mitarbeiter ab. Die Übernahme prüft zuerst, ob alle Teile vollständig da sind (sonst 422, nichts geschrieben),
übernimmt dann und räumt die Zwischenablage auf.

Die Übernahme bekommt `stand` aus der Vorschau zurück und weist mit **409** ab, wenn sich die Daten inzwischen geändert
haben. Sie schreibt das **Protokoll** (gleiche Einträge wie die bisherige Aktion). Die bisherigen Aktionen rufen dieselben
Speicherfunktionen auf – je Importart gibt es genau eine Prüf- und Speicherlogik.

## Vertrag des Lesers (Browser)

`window.WA.importLeser[<id>] = { lesen(dateien) → { daten, zeilen, fehler: [{zeile?, schluessel?, datei?, text}], hinweise, optionen?, teile? }, nachher() }`
(`teile` nur bei Importarten mit Teilen: Kennung → Daten des Teils; bleibt im Browser, bis die Vorschau ihn verlangt)
– registriert in der Datei, in der der Leser heute schon für den Import an Ort und Stelle läuft (admin.js,
admin-verwaltung.js). Wirft der Leser, ist die Datei unlesbar oder falsch (Meldung wird angezeigt, nichts übernommen).
Vor dem Leser prüft die Zentrale einheitlich Endung, leere Datei, Größe (30 MB bzw. `maxMb`), Excel statt CSV, UTF-16 statt
UTF-8/Windows-1252 und Excel-Kennung.

## Eigene Darstellung der Vorschau (Browser, optional)

`window.WA.importDarstellung[<id>] = { html(ctx) → HTML, binden(root, ctx) }` – Datei beim Eigentümer
(`app/module/<modul>/…`, in `admin/index.html` nach `admin-import.js` geladen). Liefert die Vorschau `details`, ersetzt
`html(ctx)` die einheitlichen Zahlen, Hinweise und Zeilen; Schritte, Kopf, Optionen (außer `liste`), Fuß, Übernahme,
Fehlerbehandlung und 409 bleiben bei der Zentrale. Wirft `html`, zeigt die Zentrale die einheitliche Vorschau.

`ctx` = `{ details, vorschau, optionen, zustand, zahlen, fehler, leserHinweise, hinweiseHTML, aktualisiert, setzen(id, wert) }`:
`zustand` bleibt für den Importlauf erhalten (Filter, Suche, Fokus); `fehler` = Fehlerzeilen von Leser und Server;
`setzen` ändert eine Option und lässt die Vorschau neu rechnen – die bisherige bleibt bis dahin abgeblendet stehen
(`aktualisiert`, Übernehmen gesperrt), bei schnellem Umschalten gilt nur die letzte Anfrage. `binden` wird nach jeder
Darstellung aufgerufen (Ereignisse nur an Elementen innerhalb der eigenen Darstellung).

Heute: `angebot_preise` (app/module/angebot/preisimport.js, preisimport.css).

## Aktionen der Zentrale

| Aktion | Art | Inhalt |
| --- | --- | --- |
| `import_arten` | GET | Importarten des Nutzers (nur mit Recht), mit Wartungszustand |
| `import_pruefen` | POST | `{ art, daten, quelle, optionen }` → Vorschau |
| `import_teil` | POST | nur Importarten mit `teile`: `{ art, upload, schluessel, daten, quelle }` → Zwischenablage des Eigentümers (gleiche Prüfungen wie die Vorschau) |
| `import_uebernehmen` | POST | wie oben plus `stand` (und `upload`) → Übernahme (ggf. Passwortbestätigung) |

Heute auf der Oberfläche `angebot.eingabe` registriert (`regeln/aktionen/verwaltung.toml`); mit der Freigabe von
`verwaltung.import` ziehen sie dorthin um.

**Neue Importart:** Eintrag in `import_arten_<modul>()` des Eigentümers, Vorschau-/Übernahmefunktion dort, Leser in
`window.WA.importLeser`, bei Bedarf eine eigene Darstellung in `window.WA.importDarstellung` und – falls ein neues Recht – in
`RECHTE` von `admin-import.js` (nur Anzeige des Menüpunkts);
Test in der Gruppe des Eigentümers und in `importzentrale`.
