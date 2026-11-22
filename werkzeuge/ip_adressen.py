#!/usr/bin/env python3
"""Echte öffentliche IPv4-Adressen im Repository finden (GR-007, AGENTS.md Regel 5).

Beispielwerte in Oberflächen, Fehlertexten und Vorlagen gehören in die Dokumentationsbereiche nach RFC 5737
(192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) – so wie .env.example es vormacht. Eine echte Adresse verrät,
aus welchem Netz die Mitarbeiter kommen und welches Netz von der automatischen Sperre ausgenommen ist; app/
liegt zudem in der Dokumentwurzel der öffentlichen Angebotsseite, die Datei wäre also auch ohne Anmeldung
abrufbar (Befund 22.11.2026). Der Secret-Scan (gitleaks) sucht Geheimnismuster und kann das nicht melden.

Gemeldet wird jede IPv4-Adresse, die weder privat noch reserviert noch ein Dokumentationsbereich ist
(ipaddress.is_global) und nicht im Mehrfachversand liegt. Ausgenommen sind tests/ (synthetische Testdaten mit
eigenen Adressen) und die begründeten Einzelfälle in ERLAUBT.

  python3 werkzeuge/ip_adressen.py              prüfen (CI); 1 = Fund
  python3 werkzeuge/ip_adressen.py --selbsttest Prüflogik gegen bekannte Fälle prüfen
"""
import ipaddress
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUS = ('tests/',)        # synthetische Testdaten mit eigenen Adressen
MUSTER = re.compile(r'(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])')
# Begründete Einzelfälle (kein Netz des Betriebs)
ERLAUBT = {
    '1.0.1.1': 'Beispiel für die Länderabfrage in der Schutzzentrale (fremdes Netz in Asien, zeigt ein Land)',
}


def zu_melden(wert: str) -> bool:
    """Öffentliche IPv4-Adresse (nicht privat, reserviert, Dokumentation, Mehrfachversand) und nicht erlaubt?"""
    if wert in ERLAUBT:
        return False
    try:
        a = ipaddress.IPv4Address(wert)
    except ValueError:
        return False          # z. B. Versionsnummer mit Werten über 255
    return a.is_global and not a.is_multicast


def dateien():
    roh = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z'], capture_output=True, check=True).stdout
    for name in roh.decode('utf-8').split('\0'):
        if name and not name.startswith(AUS):
            yield name


# Prüffälle als Zahlen, damit diese Datei nicht selbst eine Adresse enthält, die sie melden würde
FAELLE = (((8, 8, 8, 8), True), ((1, 2, 3, 4), True), ((45, 60, 70, 80), True),
          ((203, 0, 113, 7), False), ((192, 0, 2, 1), False), ((198, 51, 100, 9), False),
          ((10, 0, 0, 1), False), ((127, 0, 0, 1), False), ((0, 0, 0, 0), False),
          ((169, 254, 1, 1), False), ((224, 0, 0, 1), False), ((1, 0, 1, 1), False),
          ((201, 396, 836, 938), False))   # letzter Fall: Versionsnummer, keine IPv4-Adresse


def selbsttest() -> int:
    fehler = [f'{w}: erwartet {e}' for w, e in (('.'.join(map(str, o)), e) for o, e in FAELLE)
              if zu_melden(w) is not e]
    if fehler:
        print('\n'.join(fehler))
        return 1
    print('Selbsttest in Ordnung.')
    return 0


def main() -> int:
    if '--selbsttest' in sys.argv[1:]:
        return selbsttest()
    funde = []
    for name in dateien():
        try:
            text = (ROOT / name).read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue          # Bilder, Schriften, Datenbanken
        for nr, zeile in enumerate(text.splitlines(), 1):
            for wert in MUSTER.findall(zeile):
                if zu_melden(wert):
                    funde.append(f'{name}:{nr}: öffentliche IP-Adresse {wert}')
    if funde:
        print('\n'.join(sorted(set(funde))))
        print('\nGR-007: keine echten IP-Adressen im Repository. Beispiele aus den Dokumentationsbereichen nehmen '
              '(192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24, RFC 5737).')
        return 1
    print('Keine echten öffentlichen IP-Adressen gefunden (ohne tests/).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
