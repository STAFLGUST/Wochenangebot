# Bestand: Wochenpreise und erwartete Zugänge

## Datenquelle und Geschäftsregeln

- Dieselbe WinAB-Bestandsdatei liefert beide Mengenarten. Fachlich bestätigt am 19.10.2026:
  Status **eingelagert** = vorhandener Bestand; Status **erfasst** = Ware noch nicht angekommen.
  In der vorhandenen XLS-Testdatei steht der Status in J, Ankunft in M. Der Parser erkennt die
  Spalten wie bisher über Überschriften und Datenprofile; er verwirft unbekannte Statuswerte.
- Nur eingelagerte Partien bilden `articles`, verfügbare kg und MHD-Summen. Erwartete Lieferungen
  stehen einzeln in `incoming`: `code`, `name`, `lot`, `arrival` (ISO-Datum oder null), `kg`.
  Ihre Menge wird nicht in `articles` gespeichert. Die Anzeige „Gesamt verfügbar“ summiert ausschließlich für die Übersicht eingelagerte und erfasste Mengen. Einkauf, Sonderposten und öffentliche Angebote
  verwenden unverändert ausschließlich `articles`.
- Mehrere erfasste Zeilen bleiben mehrere Lieferungen, auch bei gleichem Datum/gleicher Partie.
  Fehlende Ankunft erscheint als „ETA unbekannt“. Ein überschrittenes ETA ist kein Beleg für
  Wareneingang: Erst ein neuer Import mit Status „eingelagert“ ändert den verfügbaren Bestand.
- Artikel mit ausschließlich erwarteten Zugängen erscheinen ebenfalls. Ohne eingelagerten
  Datensatz zeigt „Eingelagerter Bestand“ einen Strich. Die Gesamtsumme umfasst dann nur die vorhandenen Zugangsdatensätze.
  Bestandsdatum und Importzeit bleiben sichtbar; dies ist kein Live-Abgleich mit WinAB.
- „Aktuell“ ist die tatsächliche ISO-Kalenderwoche in Europe/Berlin. „Vorwoche“ ist genau sieben
  Tage davor, inklusive ISO-Jahreswechsel. Ein Entwurf für eine andere Woche zählt nicht.
- Quelle sind gespeicherte Standardpreise in `historie/YYYY-WW`. Fehlt eine Woche, kann ausschließlich
  eine Veröffentlichung derselben Woche aus `angebot`/`versionen` dienen (jüngste Veröffentlichung).
  Explizit gelöschte Historienwochen werden nicht wiederhergestellt. Lesen schreibt keine Historie.
- Preisangaben werden über normalisierte Artikelnummern zugeordnet. Unterschiedliche Preise oder
  Preisbasen unter derselben Nummer werden als „mehrere Preisangaben“ angezeigt, nicht willkürlich
  ausgewählt. Nur numerische Preise mit gleicher Preisbasis werden verglichen (Genauigkeit 4 Stellen).
  Die separate Preisänderungsspalte entfällt. Anfragepreise und fehlende Preise werden nicht als null Euro gewertet.
- Standardpreise sind keine Kunden-, Sonder- oder Einkaufspreise. Abweichende Preislabels werden
  angezeigt. Die Entwurfsangaben im Artikeldialog bleiben ausdrücklich als Entwurf gekennzeichnet.

## Darstellung

Die fette Kopfzeile folgt der Reihenfolge Artikelnummer, Bezeichnung, aktueller Preis,
Vorwochenpreis, eingelagerter Bestand, kürzestes MHD, kg am kürzesten MHD, erfasster Bestand,
Gesamt verfügbar, erwartete Zugänge. Fehlende Preise erscheinen als „—“.
Erfasster Bestand summiert die vorhandenen Zugangszeilen; ohne Zeilen sind 0 kg erfasst.
Unter der Menge steht die **nächste ETA** (frühestes Ankunftsdatum ab heute, Format TT.MM.JJ). Liegen alle Ankunftsdaten
in der Vergangenheit, erscheint das späteste – farbig markiert als überschritten (noch nicht eingelagert). Zeilen ohne Datum
zählen nicht. Im Fenster „Erwartete Zugänge“ stehen Marke und Partie fett und gut lesbar unter Menge und ETA.
Gesamt verfügbar ist die Summe beider Mengenarten, einschließlich noch nicht eingetroffener Ware.
Diese Anzeigen beschreiben ausschließlich den letzten Import, keine garantierte Lieferbarkeit.
Gruppen- und Gesamtsummen, Detaildialog, CSV und Druck verwenden dieselbe Berechnung.
Zugänge werden in der Übersicht nur
als Button mit Anzahl gezeigt. Er öffnet einen Dialog mit den einzelnen Mengen und ETAs;
Escape und Schließen schließen ihn. CSV und Druck enthalten weiterhin die Lieferdetails.

## Schnittstelle und Rechte

`GET stock` bleibt nur mit `bestand.sehen` verfügbar. Das zusätzliche Antwortfeld `prices` enthält
`allowed`, `current`, `previous`; je Woche `week`, `year`, `available`, `source`, `origin`, `items`.
Jeder Preiseintrag enthält ausschließlich `code` und `price`, niemals Kundenpreisvarianten.
Ohne `preisverlauf.sehen` kommt nur `prices: {allowed: false}`; die Oberfläche zeigt fehlende Berechtigung.

`POST stock_import` behält `bestand.importieren`, POST/JSON und CSRF-Prüfung. Optionales `incoming`
ist eine Liste mit höchstens 20.000 Lieferungen. Artikelnummer, positive endliche kg-Menge (max.
10.000.000, drei Nachkommastellen), Datum 2000–2100 und Textlängen werden serverseitig validiert.
Ungültige Lieferungen verwerfen den gesamten Import. Reine Zugangsdateien sind erlaubt.

## Migration, Bereitstellung und Rückfall

Keine SQL-Schemamigration: Die vorhandene Speicherschicht speichert dasselbe erweiterte
Bestandsdokument in Dateien oder SQLite. Alte Dokumente ohne `incoming` bleiben lesbar und zeigen
„keine Zugangsdaten“. **Die Bestandsdatei nach Freigabe erneut hochladen**, um bisher verworfene
erfasste Zeilen zu übernehmen; sie können nicht aus alten Bestandsdokumenten rekonstruiert werden.

Ein neuer Import ersetzt wie bisher den gesamten Bestand einschließlich der Zugangsliste.
Alte Clients ohne `incoming` setzen die Liste leer. Ein Rückfall auf die Vorversion ignoriert das
neue Feld beim Lesen; ein Import mit der Vorversion entfernt es wieder. Danach erneut importieren.
Kein automatischer Wareneingang, keine Reservierung, keine Produktionsmigration oder Bereitstellung
durch diesen PR. Merge/Release nur über den bestehenden Freigabeprozess.

## Prüfung

`stock` prüft den echten XLS-Import und unveränderte eingelagerte Summen. `stock_overview` prüft
Wochenpreise, fehlende Historie, getrennte Mengen und Gesamtsummen, mehrere Lieferungen, unbekannte ETA, reine Zugänge, Validierung,
Rechte, keine öffentliche Auslieferung, CSV, Druck und Desktop/Mobil in hell/dunkel.
Unit-Tests prüfen außerdem J/M-Zuordnung, Kalendergrenzen, Historienlücken und mehrdeutige Preise.

## EK-Preis je Partie

Die Bestandsliste liefert je eingelagerter Partie den Einkaufspreis (Spalte „EKPreis“ bzw. „Preis“, € je kg). Er wird je
Partie als `ek` gespeichert (Erweiterung, ältere Stände haben ihn nicht). `?action=stock` liefert `ek` nur mit dem Recht
`bestand.einkaufspreise` (Standard: Bearbeiter; Administratoren immer) – sonst entfernt `stock_ohne_ek()` den Wert vor der
Antwort. Auf der öffentlichen Seite erscheint er nie.
