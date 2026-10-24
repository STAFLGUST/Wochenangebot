# Entwickler-Dokumentation der STAFL-Plattform

Diese Dokumentation erklärt den Code so, dass ein Entwickler (Mensch oder KI-Agent) ohne Vorwissen damit arbeiten kann:
lokal starten, verstehen, wo was liegt, sicher erweitern, testen und über den Release-Prozess ausliefern.

**Verbindlich** sind die Arbeitsregeln in [`AGENTS.md`](../../AGENTS.md) und das maschinenlesbare Regelwerk in
[`regeln/`](../../regeln/). Diese Dokumentation erklärt sie, ersetzt sie aber nicht.

## Lesereihenfolge

| Kapitel | Inhalt | Für wen |
| --- | --- | --- |
| [1 Schnellstart](01-schnellstart.md) | Voraussetzungen, lokal starten, erster Test, erster Pull Request | alle, zuerst |
| [2 Architektur](02-architektur.md) | Systembild, Hosts, Module, Schichten, Weg einer Anfrage | alle, zuerst |
| [3 Server](03-server.md) | PHP-API: Ablauf einer Anfrage, Aufbau, Aktionen, Speicherschicht, Konfiguration | Server |
| [4 Anmeldung und Rechte](04-anmeldung-rechte.md) | Keycloak, Sitzungen, CSRF, Host-Bindung, Rollen, Rechte, Modulzugang, Kunden | alle, die Aktionen schreiben |
| [5 Daten](05-daten.md) | Speicher-Dokumente, Aufbau, Formatregeln, Datenverantwortung | Server |
| [6 Oberflächen](06-oberflaechen.md) | Kundenseite, Eingabebereich, Dashboard, Modulseiten, Gestaltung | Browser |
| [7 Tests](07-tests.md) | Testarten, Testlauf, Tests schreiben | alle |
| [8 CI, Release und Betrieb](08-betrieb.md) | CI-Aufträge, Release-Ablauf, Server, Skripte, Notfälle | alle, Betrieb |
| [9 Anleitungen](09-anleitungen.md) | Schritt für Schritt: neue Aktion, neues Recht, neues Dokument, neues Modul, neue Ansicht … | alle |
| [10 Konventionen](10-konventionen.md) | Sprache, Namen, Code-Stil, Kommentare, Sicherheitsregeln, Dokumentationspflicht | alle |

## Nachschlagen (automatisch aus dem Code erzeugt)

| Referenz | Inhalt |
| --- | --- |
| [API-Aktionen](referenz/api.md) | jede Aktion mit Modul, Oberfläche, Art, Kennzeichen, Rechteprüfung, Datei |
| [Rechte](referenz/rechte.md) | Modulzugang und alle Rechte mit Standardrollen und Voraussetzungen |
| [Speicher-Dokumente](referenz/daten.md) | jedes Dokument mit Eigentümer, Schutzstufe, erlaubten Lesern/Schreibern |
| [Module](referenz/module.md) | Module, Oberflächen, Adressen, Entwicklungs- und Freigabestand |
| [Dateien](referenz/dateien.md) | jede Datei mit Modul und Kurzbeschreibung aus ihrem Kopfkommentar |

Die Referenz schreibt `python3 werkzeuge/doku.py erzeugen`; **die CI lehnt jeden Pull Request ab**, bei dem sie nicht zum
Code passt oder eine Code-Datei keinen beschreibenden Kopfkommentar hat (`python3 werkzeuge/doku.py pruefen`).

## Weitere Dokumente im Repository

- [`docs/architektur.md`](../architektur.md) – ausführliche Beschreibung jeder Server-Datei und der Gestaltung („was liegt wo“)
- [`docs/plattform/`](../plattform/README.md) – Zielarchitektur, Entscheidungen (ADR), Roadmap, Arbeiten mit mehreren Agenten
- [`tests/README.md`](../../tests/README.md) – alle Testgruppen mit Inhalt
- [`docs/release-freigabe.md`](../release-freigabe.md), [`docs/datenbank.md`](../datenbank.md), [`docs/testumgebung.md`](../testumgebung.md) – Betrieb
- [`mobile/LIESMICH.md`](../../mobile/LIESMICH.md) – App für iOS und Android (Expo), nutzt dieselbe API;
  [`docs/app-grundlagen.md`](../app-grundlagen.md), [`docs/app-api.md`](../app-api.md) – Grundlagen und Schnittstelle der App
- [`docs/bestell-api-v1.md`](../bestell-api-v1.md), [`docs/bestell-mailversand.md`](../bestell-mailversand.md) – Bestellungen
- [`LIESMICH.md`](../../LIESMICH.md) – Funktionen aus Sicht der Anwender

## Dokumentation aktuell halten

Jede Änderung am Code bringt ihre Dokumentation im selben Pull Request mit (Definition of Done in `AGENTS.md`):

1. `python3 werkzeuge/doku.py erzeugen` – Referenz neu schreiben (die CI prüft das).
2. Neue Datei → Kopfkommentar, dessen erster Satz sagt, was die Datei tut (die CI prüft das).
3. Geändertes Verhalten → das passende Kapitel hier anpassen (Ablauf, Regeln, Beispiele, Anleitungen) und
   `docs/architektur.md` bzw. `LIESMICH.md`, wo betroffen. Prüfer achten im Pull Request darauf (Kästchen in der Vorlage).
