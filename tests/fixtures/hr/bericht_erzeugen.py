"""Erzeugt die synthetische Testdatei Abwesenheitsbericht_Muster.xlsx im Aufbau des Abwesenheitsberichts der Zeiterfassung
(Importvorlage für Urlaubs- und Krankheitstage): Kopfzeile 1 (Vorname, Nachname, Name (Abwesenheit), Abwesenheitsvergütung,
Startdatum, Enddatum, Dauer, Mitarbeiternummer, Zweite Mitarbeiternummer, Abteilung, Standort, Gesamt); je Mitarbeiter eine
Zeile mit Namen, Nummer (Text), Abteilung und Gesamtstunden, darunter die Abwesenheiten mit Datum (Format dd-MM-yyyy).
Nur erfundene Namen (GR-007). Passt zu Urlaub_Muster_2025.xlsx (gleiche Namen, Jahr 2025).

    python3 tests/fixtures/hr/bericht_erzeugen.py
"""
import datetime as dt
import os

import openpyxl

KOPF = ['Vorname', 'Nachname', 'Name (Abwesenheit)', 'Abwesenheitsvergütung', 'Startdatum', 'Enddatum', 'Dauer', 'Mitarbeiternummer',
        'Zweite Mitarbeiternummer', 'Abteilung', 'Standort', 'Gesamt']
U = ('Urlaub ', 'Abgezogen vom Urlaub')          # wie im Original mit Leerzeichen
F = ('Feiertag', 'Bezahlte Abwesenheit')
KA = ('Krank mit AU', 'Bezahlte Abwesenheit')
KO = ('Krank ohne AU', 'Abgezogen vom Urlaub')
d = dt.datetime
# (Vorname, Nachname, Nummer, Abteilung, [(Art, von, bis)])
PERSONEN = [
    ('Anna', 'Beispiel', '101', 'Geschäftsführung', [(F, d(2025, 1, 1), d(2025, 1, 1)), (U, d(2025, 1, 13), d(2025, 1, 17))]),   # wie in der Excel-Planung
    ('Bernd', 'Muster', '102', 'Verwaltung', [(U, d(2025, 1, 20), d(2025, 1, 21)),                                                 # Planung: K – abweichend
                                              (KO, d(2025, 3, 5), d(2025, 3, 5))]),                                                 # zählt gegen den Urlaub
    ('Karla', 'Probe', '103', 'Verwaltung', [(U, d(2025, 2, 3), d(2025, 2, 4)), (U, d(2025, 3, 17), d(2025, 3, 18))]),           # Schreibweise ≠ „Carla“
    ('Erika', 'Editor', '104', 'Verwaltung', [(KA, d(2025, 2, 10), d(2025, 2, 14)), (U, d(2025, 3, 24), d(2025, 3, 28)),
                                              (('Elternzeit', 'Unbezahlt'), d(2025, 3, 31), d(2025, 3, 31))]),                     # unbekannte Art
    ('Hans', 'Neumann', '105', 'Produktion', [(U, d(2025, 2, 27), d(2025, 3, 4)),                                                  # über das Wochenende
                                              (U, 'kein Datum', d(2025, 3, 10))]),                                                   # ungültig
    ('Ina', 'Ohnenummer', '', 'Produktion', [(F, d(2025, 1, 1), d(2025, 1, 1))]),                                                    # ohne Nummer, nur Feiertag
]

wb = openpyxl.Workbook()
ws = wb.active
ws.title = 'Abwesenheitsbericht'
ws.append(KOPF)
for vor, nach, nr, abt, abw in PERSONEN:
    stunden = 0
    zeilen = []
    for (art, verg), von, bis in abw:
        tage = (bis - von).days + 1 if isinstance(von, dt.datetime) else 1
        stunden += 8 * tage
        zeilen.append([None, None, art, verg, von, bis, f'{8 * tage:02d}:00'])
    ws.append([vor, nach, None, None, None, None, None, nr or None, None, abt, 'STAFL ', f'{stunden}:00'])
    for z in zeilen:
        ws.append(z)
for zeile in ws.iter_rows(min_row=2):
    for c in zeile[4:6]:
        if isinstance(c.value, dt.datetime):
            c.number_format = 'dd-MM-yyyy'
wb.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Abwesenheitsbericht_Muster.xlsx'))
