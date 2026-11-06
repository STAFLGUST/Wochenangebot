#!/usr/bin/env python3
"""Netzsperre für bunny.net (deploy/cdn_netzsperre.py): Liste prüfen, zusammenführen, abrufen und Regelwerk – und das Regelwerk
mit echtem nftables in abgeschotteten Netz-Namensräumen.

Liste: nur öffentliche Adressen der richtigen Familie (Dokumentationsnetze nur mit WA_TESTNETZE=1), kaputte Antworten (kein
JSON, zu wenige IPv4, viele ungültige Einträge) verworfen; eine Adresse bleibt 14 Tage nach dem letzten Erscheinen; abrufen
behält bei Fehlern die bisherige Liste (Ausgang 1) und meldet ohne nutzbare Liste Ausgang 2; IPv6-Fehler lassen die
bisherige IPv6-Liste stehen; Datei nur für den Besitzer lesbar.
Regelwerk: „drop“ nur im Modus „an“, nur die angegebene Schnittstelle, Ports 80/443, Weiterleitung (ursprünglicher Zielport)
und Host; ungültige Schnittstelle oder leere Liste abgelehnt.
Netz (braucht nft und ip, läuft mit `unshare -rn` bzw. `sudo -n unshare -n`; in der CI Pflicht über WA_NETZ_PFLICHT=1):
Besucher → Server-Schnittstelle „eth0“ → DNAT 443 an einen „Container“ (wie Docker) und Dienst des Hosts an 80 (wie der
Docker-Proxy) sowie IPv6 an 80; ohne Regeln und im Modus „beobachten“ alles offen (Zähler steigen), im Modus „an“ nur die
Adresse aus der Liste, andere Ports bleiben offen; erneutes Setzen ersetzt atomar; Löschen der Tabelle öffnet wieder.
Alle Adressen aus den Dokumentationsnetzen (GR-007)."""
import datetime as dt
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location("cdn_netzsperre", REPO / "deploy" / "cdn_netzsperre.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)

PASS = FAIL = 0


def check(name, ok, info=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("PASS", name)
    else:
        FAIL += 1
        print("FAIL", name, info)


def doku4(n, start=0):
    """n verschiedene IPv4-Adressen aus den drei Dokumentationsnetzen."""
    netze = ["192.0.2.", "198.51.100.", "203.0.113."]
    return [netze[i // 256] + str(i % 256) for i in range(start, start + n)]


os.environ["WA_TESTNETZE"] = "1"

# ── Liste prüfen ──
gut = doku4(150)
check("gültige Liste angenommen, sortiert, ohne Doppelte", ns.pruefe_liste(json.dumps(gut + gut[:3]), 4) == ns.pruefe_liste(json.dumps(sorted(gut)), 4)
      and len(ns.pruefe_liste(json.dumps(gut), 4)) == 150)
for name, roh in [("kein JSON", b"<html>"), ("JSON ohne Liste", json.dumps({"a": 1})),
                  ("zu wenige IPv4", json.dumps(doku4(99))),
                  ("viele ungültige Einträge", json.dumps(gut + ["kaputt"] * 6))]:
    try:
        ns.pruefe_liste(roh, 4)
        check("abgelehnt: " + name, False)
    except ValueError:
        check("abgelehnt: " + name, True)
mit = ns.pruefe_liste(json.dumps(gut + ["10.0.0.1", "127.0.0.1", "2001:db8::1", "x"]), 4)
check("private, Loopback, IPv6 und Text in der IPv4-Liste übersprungen (bis 5)", len(mit) == 150 and "10.0.0.1" not in mit and "127.0.0.1" not in mit)
check("IPv6-Liste: nur IPv6, normalisiert", ns.pruefe_liste(json.dumps(["2001:DB8::0:5", "192.0.2.1"]), 6) == ["2001:db8::5"])
os.environ["WA_TESTNETZE"] = "0"
try:
    ns.pruefe_liste(json.dumps(gut), 4)
    check("ohne WA_TESTNETZE: Dokumentationsnetze nicht öffentlich – abgelehnt", False)
except ValueError:
    check("ohne WA_TESTNETZE: Dokumentationsnetze nicht öffentlich – abgelehnt", True)
os.environ["WA_TESTNETZE"] = "1"

# ── Zusammenführen (14 Tage) ──
t = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)
bisher = {"192.0.2.1": "2026-11-19T12:00:00Z", "192.0.2.2": "2026-11-07T12:00:00Z", "192.0.2.3": "2026-11-05T12:00:00Z"}
erg, neu, weg = ns.zusammenfuehren(bisher, ["192.0.2.1", "192.0.2.9"], t)
check("zuletzt vor 13 Tagen gesehen bleibt, vor 15 Tagen entfällt", "192.0.2.2" in erg and "192.0.2.3" not in erg, erg)
check("neue Adresse aufgenommen, gesehene aktualisiert", erg["192.0.2.9"] == "2026-11-20T12:00:00Z" and erg["192.0.2.1"] == "2026-11-20T12:00:00Z")
check("Zählung neu/entfallen", neu == 1 and weg == 1, (neu, weg))
check("Netze zusammengefasst", ns.netze(["192.0.2.%d" % i for i in range(256)]) == ["192.0.2.0/24"])

# ── Abrufen ──
tmp = Path(tempfile.mkdtemp())
try:
    q4, q6, liste = tmp / "v4.json", tmp / "v6.json", tmp / "liste.json"
    os.environ["WA_BUNNY_V4"], os.environ["WA_BUNNY_V6"] = q4.as_uri(), q6.as_uri()
    q4.write_text(json.dumps(doku4(120)))
    q6.write_text(json.dumps(["2001:db8::1", "2001:db8::2"]))
    check("abrufen: Erfolg (0)", ns.abrufen(str(liste)) == 0)
    d = json.loads(liste.read_text())
    check("abrufen: 120 IPv4, 2 IPv6, Zeit gesetzt, kein Fehler", len(d["v4"]) == 120 and len(d["v6"]) == 2 and d["abgerufen"] and d["fehler"] is None)
    check("Liste nur für den Besitzer lesbar", stat.S_IMODE(liste.stat().st_mode) == 0o600)
    check("faellig: frisch → nein, nach 0 Stunden → ja", not ns.faellig(str(liste), 6) and ns.faellig(str(liste), 0))
    q4.write_text("<html>Wartung</html>")
    check("abrufen mit kaputter Antwort: bisherige Liste bleibt (1)", ns.abrufen(str(liste)) == 1)
    d = json.loads(liste.read_text())
    check("… Liste unverändert, Fehler vermerkt", len(d["v4"]) == 120 and "IPv4" in (d["fehler"] or ""))
    q4.write_text(json.dumps(doku4(110, 120)))
    q6.write_text("kaputt")
    check("IPv6 kaputt, IPv4 gut: Erfolg (0)", ns.abrufen(str(liste)) == 0)
    d = json.loads(liste.read_text())
    check("… IPv4 ergänzt (alte bleiben 14 Tage), IPv6 bleibt", len(d["v4"]) == 230 and len(d["v6"]) == 2 and "IPv6" in (d["fehler"] or ""))
    leer = tmp / "leer.json"
    q4.unlink()
    check("ohne nutzbare Liste und ohne Quelle: Ausgang 2", ns.abrufen(str(leer)) == 2)
    check("faellig ohne Liste: ja", ns.faellig(str(leer), 6))

    # ── Regelwerk ──
    an = ns.regelwerk_aus_liste(str(liste), "an", "eth0")
    beob = ns.regelwerk_aus_liste(str(liste), "beobachten", "eth0")
    check("Modus an verwirft, beobachten nicht", "\t\tdrop" in an and "drop" not in beob.replace("# Modus", ""))
    check("nur die angegebene Schnittstelle, Ports 80/443, Weiterleitung und Host",
          an.count('iifname "eth0"') == 4 and "ct original proto-dst { 80, 443 }" in an and "th dport { 80, 443 }" in an
          and "hook forward" in an and "hook input" in an)
    check("atomar ersetzt (add/delete/table in einer Datei)", an.index("add table inet stafl_netzsperre") < an.index("delete table inet stafl_netzsperre") < an.index("table inet stafl_netzsperre {"))
    for name, args in [("Schnittstelle mit Leerzeichen", ("an", "eth0 x", ["192.0.2.1/32"], [])),
                       ("Schnittstelle mit Anführungszeichen", ("an", 'eth0"', ["192.0.2.1/32"], [])),
                       ("leere IPv4-Liste", ("an", "eth0", [], [])), ("unbekannter Modus", ("vielleicht", "eth0", ["192.0.2.1/32"], []))]:
        try:
            ns.regelwerk(*args)
            check("Regelwerk abgelehnt: " + name, False)
        except ValueError:
            check("Regelwerk abgelehnt: " + name, True)
    try:
        ns.regelwerk_aus_liste(str(leer), "an", "eth0")
        check("Regelwerk ohne nutzbare Liste abgelehnt", False)
    except ValueError:
        check("Regelwerk ohne nutzbare Liste abgelehnt", True)

    # ── Bericht ──
    zeilen = ["[1.0] stafl-netzsperre: IN=eth0 OUT= SRC=198.51.100.20 DST=192.0.2.1 PROTO=TCP SPT=5 DPT=443"] * 3 \
        + ["stafl-netzsperre: IN=eth0 SRC=192.0.2.5 DST=192.0.2.1 PROTO=TCP DPT=443", "andere Zeile SRC=1.1.1.1"]
    b = ns.bericht(str(liste), zeilen)
    check("Bericht: fremde Versuche gezählt, Edge-Server erkannt, fremde Zeilen ignoriert",
          "4 von 2 Adressen" in b and "198.51.100.20" in b and "inzwischen in der bunny-Liste" in b and "1.1.1.1" not in b, b)
    check("Bericht ohne Versuche", "keine" in ns.bericht(str(liste), []))
finally:
    shutil.rmtree(tmp)

# ── Mit echtem nftables im Netz-Namensraum ──
NETZ = r'''
set -eu
PIDS=""
aufraeumen() { for p in $PIDS; do kill "$p" 2>/dev/null || true; done; }
trap aufraeumen EXIT
ip link set lo up
unshare -n sleep 120 & BES=$!; PIDS="$PIDS $BES"
unshare -n sleep 120 & CON=$!; PIDS="$PIDS $CON"
sleep 0.3
ip link add eth0 type veth peer name aussen
ip link set aussen netns "$BES"
ip link add br-x type veth peer name c0
ip link set c0 netns "$CON"
V6=0; [ -d /proc/sys/net/ipv6 ] && V6=1   # ohne IPv6 im Kernel: IPv6-Probe „nv“
ip addr add 192.0.2.1/24 dev eth0; ip link set eth0 up
[ $V6 = 0 ] || ip -6 addr add 2001:db8:1::1/64 dev eth0 nodad
ip addr add 10.9.0.1/24 dev br-x; ip link set br-x up
echo 1 > /proc/sys/net/ipv4/ip_forward
ip route add 203.0.113.10 via 192.0.2.2; ip route add 198.51.100.20 via 192.0.2.2
nsenter -t "$BES" -n sh -c 'ip link set lo up; ip addr add 192.0.2.2/24 dev aussen; ip addr add 203.0.113.10/32 dev aussen
  ip addr add 198.51.100.20/32 dev aussen; ip link set aussen up; ip route add default via 192.0.2.1'
[ $V6 = 0 ] || nsenter -t "$BES" -n ip -6 addr add 2001:db8:1::2/64 dev aussen nodad
nsenter -t "$CON" -n sh -c 'ip link set lo up; ip addr add 10.9.0.2/24 dev c0; ip link set c0 up; ip route add default via 10.9.0.1'
nft -f "$1/nat.nft"
nsenter -t "$CON" -n python3 "$1/dienst.py" 0.0.0.0 443 & PIDS="$PIDS $!"
python3 "$1/dienst.py" 0.0.0.0 80 & PIDS="$PIDS $!"
python3 "$1/dienst.py" 0.0.0.0 8080 & PIDS="$PIDS $!"
if [ $V6 = 1 ]; then python3 "$1/dienst.py" :: 80 & PIDS="$PIDS $!"; fi
sleep 0.6
probe() { case "$2" in *:*) [ $V6 = 1 ] || { echo nv; return; } ;; esac; nsenter -t "$BES" -n python3 "$1/probe.py" "$2" "$3" "$4"; }
runde() {
  echo "$1 bunny443=$(probe "$2" 203.0.113.10 192.0.2.1 443) fremd443=$(probe "$2" 198.51.100.20 192.0.2.1 443)" \
    "bunny80=$(probe "$2" 203.0.113.10 192.0.2.1 80) fremd80=$(probe "$2" 198.51.100.20 192.0.2.1 80)" \
    "fremd8080=$(probe "$2" 198.51.100.20 192.0.2.1 8080) fremd6=$(probe "$2" 2001:db8:1::2 2001:db8:1::1 80)" \
    "zaehler=$(nft list table inet stafl_netzsperre 2>/dev/null | sed -n 's/.*counter packets \([0-9]*\).*/\1/p' | awk '{s += $1} END {print s + 0}')"
}
runde ohne "$1"
nft -f "$1/beobachten.nft"; runde beobachten "$1"
nft -f "$1/an.nft"; runde an "$1"
nft -f "$1/an.nft"; runde an2 "$1"
nft delete table inet stafl_netzsperre; runde geloescht "$1"
'''
DIENST = """import socket, sys
fam = socket.AF_INET6 if ":" in sys.argv[1] else socket.AF_INET
s = socket.socket(fam); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
if fam == socket.AF_INET6: s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
s.bind((sys.argv[1], int(sys.argv[2]))); s.listen(16)
while True:
    c, _ = s.accept(); c.sendall(b"ok"); c.close()
"""
PROBE = """import socket, sys
fam = socket.AF_INET6 if ":" in sys.argv[1] else socket.AF_INET
s = socket.socket(fam); s.settimeout(1.5); s.bind((sys.argv[1], 0))
try:
    s.connect((sys.argv[2], int(sys.argv[3]))); print("offen" if s.recv(2) == b"ok" else "anders")
except OSError:
    print("zu")
"""
NAT = """table ip probenat {
	chain pre {
		type nat hook prerouting priority dstnat; policy accept;
		iifname "eth0" tcp dport 443 dnat to 10.9.0.2:443
	}
}
"""


def laeufer():
    if not (shutil.which("nft") and shutil.which("ip") and shutil.which("unshare") and shutil.which("nsenter")):
        return None
    for vor in (["unshare", "-rn"], ["sudo", "-n", "unshare", "-n"]):
        try:
            if subprocess.run(vor + ["nft", "list", "ruleset"], capture_output=True, timeout=20).returncode == 0:
                return vor
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


vor = laeufer()
if vor is None:
    if os.environ.get("WA_NETZ_PFLICHT") == "1":
        check("Netz-Namensraum mit nft verfügbar (WA_NETZ_PFLICHT=1)", False, "nft/ip/unshare fehlen oder keine Rechte")
    else:
        print("SKIP Netztest: nft, ip oder ein Netz-Namensraum nicht verfügbar")
else:
    arbeit = Path(tempfile.mkdtemp())
    os.chmod(arbeit, 0o755)
    try:
        for name, inhalt in {"netz.sh": NETZ, "dienst.py": DIENST, "probe.py": PROBE, "nat.nft": NAT,
                             "an.nft": ns.regelwerk("an", "eth0", ["203.0.113.0/25"], []),
                             "beobachten.nft": ns.regelwerk("beobachten", "eth0", ["203.0.113.0/25"], [])}.items():
            (arbeit / name).write_text(inhalt)
            os.chmod(arbeit / name, 0o644)
        p = subprocess.run(vor + ["sh", str(arbeit / "netz.sh"), str(arbeit)], capture_output=True, text=True, timeout=120)
        runden = {}
        for z in p.stdout.splitlines():
            teile = z.split()
            if teile and teile[0] in ("ohne", "beobachten", "an", "an2", "geloescht"):
                runden[teile[0]] = dict(x.split("=", 1) for x in teile[1:])
        ok = p.returncode == 0 and len(runden) == 5
        check("Netztest gelaufen (%s)" % " ".join(vor), ok, p.stdout[-2000:] + p.stderr[-2000:])
        if ok:
            r = runden
            v6 = r["ohne"]["fremd6"] != "nv"
            if not v6:
                print("HINWEIS IPv6 im Kernel dieser Umgebung nicht verfügbar – IPv6-Probe übersprungen (in der CI geprüft)")
            alle = ("bunny443", "fremd443", "bunny80", "fremd80", "fremd8080") + (("fremd6",) if v6 else ())
            check("ohne Regeln: alles offen (DNAT wie Docker, Host, IPv6)", all(r["ohne"][k] == "offen" for k in alle), r["ohne"])
            check("beobachten: nichts verworfen, fremde Verbindungen gezählt",
                  all(r["beobachten"][k] == "offen" for k in alle) and int(r["beobachten"]["zaehler"]) >= (3 if v6 else 2), r["beobachten"])
            check("an: Edge-Server aus der Liste kommt an 443 (Weiterleitung) und 80 (Host) durch",
                  r["an"]["bunny443"] == "offen" and r["an"]["bunny80"] == "offen", r["an"])
            check("an: fremde Adresse an 443 und 80 verworfen, IPv6 ohne Liste verworfen",
                  r["an"]["fremd443"] == "zu" and r["an"]["fremd80"] == "zu" and r["an"]["fremd6"] in ("zu", "nv"), r["an"])
            check("an: andere Ports unberührt (8080)", r["an"]["fremd8080"] == "offen", r["an"])
            check("erneut gesetzt: gleiches Verhalten (atomar ersetzt)",
                  {k: r["an2"][k] for k in alle} == {k: r["an"][k] for k in alle}, r["an2"])
            check("Tabelle gelöscht: wieder alles offen", all(r["geloescht"][k] == "offen" for k in alle), r["geloescht"])
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)

print("cdn_netzsperre: %d bestanden, %d fehlgeschlagen" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
