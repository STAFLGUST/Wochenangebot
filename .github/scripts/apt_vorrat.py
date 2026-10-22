#!/usr/bin/env python3
"""Paketvorrat für die CI: heruntergeladene Debian-Pakete (.deb) zwischen Läufen aufbewahren.

Der Ubuntu-Spiegel der GitHub-Runner liefert zeitweise nur 45–60 kB/s (bis zu 13 Minuten für ~40 MB Pakete).
Deshalb legt der Workflow „Zwischenspeicher“ die Pakete im GitHub-Zwischenspeicher ab; die Testaufträge legen sie vor
der Installation in den Paket-Ordner von apt.

Sicherheit: apt prüft Pakete, die bereits im Paket-Ordner liegen, NICHT noch einmal (ausprobiert: ein verändertes
Paket wurde ohne Meldung installiert). Darum übernimmt `einsetzen` nur Dateien, deren SHA-256 genau zum Eintrag in
der signierten Paketliste passt (`apt-cache show`, nach `apt-get update`). Alles andere wird verworfen und von apt
normal heruntergeladen – im Zweifel also wie ohne Zwischenspeicher.

    sudo python3 -I .github/scripts/apt_vorrat.py einsetzen <ordner>   # geprüfte Pakete → /var/cache/apt/archives
    sudo python3 -I .github/scripts/apt_vorrat.py sammeln <ordner>     # /var/cache/apt/archives/*.deb → <ordner>

Umgebung: APT_ARCHIV (Paket-Ordner von apt, Standard /var/cache/apt/archives), APT_CACHE (Befehl, Standard apt-cache).
Läuft immer erfolgreich durch (Fehler → Hinweis, apt lädt dann selbst), außer bei falschem Aufruf.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.parse

ARCHIV = os.environ.get('APT_ARCHIV', '/var/cache/apt/archives')
APT_CACHE = os.environ.get('APT_CACHE', 'apt-cache')


def dateiname_lesen(name):
    """„paket_version_arch.deb“ (Version mit %3a statt „:“) → (paket, version, arch) oder None."""
    if not name.endswith('.deb') or '/' in name:
        return None
    teile = name[:-4].split('_')
    if len(teile) != 3 or not all(teile):
        return None
    return teile[0], urllib.parse.unquote(teile[1]), teile[2]


def eintraege(text):
    """Ausgabe von `apt-cache show` → {(paket, version, arch): {sha256, …}}."""
    ergebnis = {}
    for block in text.split('\n\n'):
        felder = {}
        for zeile in block.splitlines():
            if ':' in zeile and not zeile.startswith(' '):
                k, v = zeile.split(':', 1)
                felder[k.strip()] = v.strip()
        if {'Package', 'Version', 'Architecture', 'SHA256'} <= felder.keys():
            schluessel = (felder['Package'], felder['Version'], felder['Architecture'])
            ergebnis.setdefault(schluessel, set()).add(felder['SHA256'].lower())
    return ergebnis


def sha256(pfad):
    h = hashlib.sha256()
    with open(pfad, 'rb') as f:
        for stueck in iter(lambda: f.read(1 << 20), b''):
            h.update(stueck)
    return h.hexdigest()


def einsetzen(ordner):
    dateien = sorted(f for f in os.listdir(ordner) if os.path.isfile(os.path.join(ordner, f))) if os.path.isdir(ordner) else []
    pakete = {f: dateiname_lesen(f) for f in dateien}
    gesucht = sorted({f'{p[0]}={p[1]}' for p in pakete.values() if p})
    bekannt = {}
    if gesucht:
        # Unbekannte Versionen (inzwischen aktualisiert) melden Fehler – die übrigen Einträge gelten trotzdem.
        r = subprocess.run([APT_CACHE, 'show', *gesucht], capture_output=True, text=True)
        bekannt = eintraege(r.stdout)
    uebernommen, verworfen = 0, []
    for datei, paket in pakete.items():
        quelle = os.path.join(ordner, datei)
        if paket and paket in bekannt and sha256(quelle) in bekannt[paket]:
            shutil.copyfile(quelle, os.path.join(ARCHIV, datei))
            uebernommen += 1
        else:
            verworfen.append(datei)
    print(f'Paketvorrat: {uebernommen} Pakete geprüft übernommen, {len(verworfen)} verworfen (veraltet oder Prüfsumme passt nicht).')
    for datei in verworfen[:20]:
        print(f'  verworfen: {datei}')
    return uebernommen, verworfen


def sammeln(ordner):
    os.makedirs(ordner, exist_ok=True)
    n = 0
    for datei in sorted(os.listdir(ARCHIV)):
        if dateiname_lesen(datei) and os.path.isfile(os.path.join(ARCHIV, datei)):
            shutil.copyfile(os.path.join(ARCHIV, datei), os.path.join(ordner, datei))
            n += 1
    groesse = sum(os.path.getsize(os.path.join(ordner, f)) for f in os.listdir(ordner))
    print(f'Paketvorrat: {n} Pakete gesammelt ({groesse / 1e6:.1f} MB) in {ordner}')
    return n


def main(argv):
    if len(argv) != 3 or argv[1] not in ('einsetzen', 'sammeln'):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        (einsetzen if argv[1] == 'einsetzen' else sammeln)(argv[2])
    except Exception as e:   # nie den Testauftrag abbrechen: apt lädt fehlende Pakete selbst
        print(f'::warning::Paketvorrat nicht nutzbar ({e!r}) – apt lädt die Pakete selbst.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
