# Funktionen: Sicherheit (`sicherheit`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

5 Dateien, 106 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/sicherheit.php`

_Aktionen des Moduls Sicherheit (Oberfläche sicherheit.intern, sicherheit.dashboard-stafl.de; docs/plattform/modul-sicherheit.md)_

- `sicherheit_rechte(u)` – Rechte im Modul für die Oberfläche (Anzeige; geprüft wird je Aktion)

## `app/module/sicherheit/sicherheit.js`

_STAFL-Plattform · Sicherheit (Modul sicherheit, Oberfläche sicherheit.intern; docs/plattform/modul-sicherheit.md) Reiter_

**Schnittstelle**

- `api(action, {…})`
- `aufruf(action, opts, merken)` – Aufruf mit Bestätigung: Passwort im Dialog (Testserver, alter Eingabebereich) bzw. erneute Anmeldung bei Keycloak. merken: Entwurf, der nach dem Rücksprung …

**Hinweise, Dialog**

- `toast(text, fehler)`
- `dialog(html, {…})` – Dialog öffnen bzw. Inhalt ersetzen (nächster Schritt); Fokus auf das erste Eingabefeld bzw. den Hauptknopf
- `dialogZu()`
- `lauf(b, fn)` – Knopf während eines Vorgangs sperren; Fehler im Dialog bzw. als Hinweis zeigen
- `frage(titel, text, ja, gefahr)` – Rückfrage im Dialog (ersetzt dessen Inhalt; kein zweiter Dialog)
- `passwortBestaetigen()` – Passwortbestätigung (Testserver/alter Eingabebereich) im selben Dialog: Ist ein Formular offen, legt sich der Schritt darüber und das Formular bleibt mit …
- `herunterladen(name, inhalt, typ)`

**Rahmen: Anmeldung, Fehler, Reiter, Notfallband**

- `zeigeAnmeldung()`
- `fehler(t)`
- `zeigeTab(t)`
- `notfallBand()`
- `probeBand()` – Offener Probealarm (Übung): Band in allen Reitern, bis man ihn als „gesehen“ bestätigt
- `lageLaden()`

**gemeinsame Bausteine**

- `sicherungKarte(b, ziel)`
- `bereitstellungKarte(r, ziel)`
- `verlaufSvg(tl)`
- `evDialog(e)`

**Lagebild**

- `lageTab()`
- `berichtBlock()` – Wochenbericht: Versand, Empfänger, letzter Versand; Ansehen im Dialog (wie die E-Mail)
- `bereitBlock()` – Bereitschaft: letzter Probealarm, Leitfaden und Ansprechpartner
- `berichtDialog()`
- `gesamt()`
- `abwehrHtml(L, K)` – Abwehr der letzten 24 Stunden: Angriffsmuster, abgewiesene Anfragen, gesperrte Adressen und Verlauf je Stunde
- `konsoleHtml()` – Notfall-Konsole im Lagebild: Zustand, Auslösen (Recht), Probealarm, Leitfaden, letzte Übung
- `browserPruefungen()` – Prüfungen aus Sicht des Browsers: Sicherheits-Header, gesperrte Ordner, Uhrzeit
- `cfKnopf()` – Konfigurationsprüfung: standardmäßig nur Hinweise und Kritisches, „Alle anzeigen“ blendet die erfüllten Prüfungen ein
- `topIpDialog(x)`

**Notfall**

- `notfallTab()`
- `laufzeit(seit)` – Laufzeit des Notfalls (Std:Min:Sek), jede Sekunde neu – nur solange der Reiter Notfall sichtbar ist
- `laufzeitStarten()`

**Leitfaden für den Ernstfall (im Notfall abhakbar)**

- `leitfadenHtml()`
- `leitfadenNeu(fokus)`
- `leitfadenDialog()`

**Probealarm (Übung ohne Wirkung)**

- `probenHtml()`
- `probeDialog()`
- `probeErgebnis(p, neu)`
- `dauerText(a, b)`
- `notfallVerlaufDialog(v)`
- `notfallAuslosen(entwurf)` – Auslösen in Schritten: 1 Wirkung → 2 Grund, Optionen, Bestätigungswort → 3 Bestätigung (Passwort bzw. erneute Anmeldung)
- `haltenStart(k)`
- `haltenStopp()`
- `entwurfFortsetzen()`
- `notfallBeenden()`

**Firewall & Sperren**

- `fwLaden(mitSec)`
- `firewallTab()`
- `fwZeichnen()`
- `fwLive()`
- `fwUebernehmen(r)`
- `fwSperrDialog(ip, grund)`
- `fwEinstellungen()`

**Anmeldung & Sitzungen**

- `sitzungenTab()`

**Dateiprüfung**

- `dateiTab(lauf_)`
- `befundDialog(x)`

**Ereignisse**

- `ereignisseTab()`
- `exportDialog()`

**Einstellungen & Vorlagen**

- `einstellungenTab()`
- `einstZeichnen()`
- `berichtEinstellen()`
- `vorlageDialog(k)`
- `importDialog()`
- `secSpeichern(aenderung, text)` – Speichern der Einstellungen: immer vollständig (security_save erwartet alle Felder)
- `anmeldungDialog()`
- `ipDialog()`
- `geoDialog()` – Ländersperre mit Auswahl: Schnellauswahl nach Kontinent und Gruppe (ein Klick wählt alle, ein zweiter keines), Liste nach Kontinenten gegliedert, Suche nach …
- `geoListe()`
- `geoAuffrischen()`
- `bstDialog()`

**Konten: privilegierte und ungenutzte**

- `kontenTab()`
- `ungenutztHtml(U)`
- `deaktDialog(k)`
- `kontoDialog(k)`

**System: Betrieb, Wartung, Module und Freigaben, Diagnose (nur Administratoren)**

- `systemTab()`
- `systemKarten(d)`
- `systemWartung(d)`
- `syBereiche()`
- `systemModule()`
- `systemVerlauf(d)`
- `systemZeichnen()`
- `systemEntwurf()` – Entwurf nach der erneuten Anmeldung (Keycloak) wieder öffnen – mit Hinweis, dass nur noch gespeichert werden muss
- `sySpeichern(action, body, entwurf, text)`
- `kundenDialog(modus, werte, hinweis)` – Wartungsmodus der Angebotsseite (wartung_save): an, Hinweis ändern, aus
- `eingabeDialog(modus, werte, hinweis)` – Wartung des Eingabebereichs (modul_wartung_save, immer mit Bestätigung): starten bzw. planen, ändern, beenden
- `modulDialog(ziel, werte, hinweis)` – Freigabe und Tester eines Bereichs (modul_freigabe_save, modul_tester_save – getrennt gespeichert, je mit Bestätigung)
- `diagnose(k, knopf)`

**Hell/Dunkel**

- `themaKnopf()`

**Start**

- `start()`

## `tests/e2e/test_notfall.py`

_Notfallmodus (Modul Sicherheit, lib/notfall.php, docs/plattform/modul-sicherheit.md)._

- `check(n, c, i)`
- `totp(secret)`
- `doc(name)`

## `tests/e2e/test_sicherheit_bereitschaft.py`

_Bereitschaft im Modul Sicherheit (lib/bereitschaft.php, docs/plattform/modul-sicherheit.md §8)._

- `check(n, c, i)`
- `doc(name)`
- `berlin()`
- `woche()`
- `anmelden(user, pw, ip, breite, thema, hoehe, hash_)`
- `tab(pg, t)`
- `dialog_zu(pg)`
- `breit_ok(pg)`

## `tests/e2e/test_sicherheit_modul.py`

_Modul Sicherheit (Oberfläche sicherheit.intern unter /module/sicherheit/, docs/plattform/modul-sicherheit.md)._

- `check(n, c, i)`
- `doc(name)`
- `anmelden(user, pw, ip, breite, thema, hoehe, ziel)`
- `tab(pg, t)`
- `dialog_zu(pg)`
- `halten(pg)` – Notfall auslösen: Knopf gedrückt halten, bis der Dialog „Notfallmodus ist aktiv“ zeigt (1,5 s), dann loslassen
