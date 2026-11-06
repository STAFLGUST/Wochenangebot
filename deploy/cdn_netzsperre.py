#!/usr/bin/env python3
"""Netzsperre am Server: Port 80/443 nur noch für die Edge-Server von bunny.net – Liste und Regeln (nftables).

Aufgerufen von deploy/cdn-netzsperre.sh (als root auf dem Server, Anleitung: docs/bunny-cdn.md, Abschnitt 7). Nur Python-
Standardbibliothek, führt selbst nie nft aus.

  python3 deploy/cdn_netzsperre.py abrufen   LISTE              bunny-Liste holen, prüfen, mit der bisherigen zusammenführen
  python3 deploy/cdn_netzsperre.py faellig   LISTE STUNDEN      Ausgang 0, wenn die Liste fehlt oder älter ist
  python3 deploy/cdn_netzsperre.py regelwerk LISTE MODUS IF     nft-Regelwerk ausgeben (MODUS beobachten|an, IF = Netzwerkschnittstelle)
  python3 deploy/cdn_netzsperre.py bericht   LISTE              Zusammenfassung; liest Kernel-Protokollzeilen der Sperre von stdin

Liste (LISTE, JSON, nur root lesbar): {"version": 1, "abgerufen": Zeit, "versuch": Zeit, "fehler": Text|null,
"v4": {Adresse: zuletzt gesehen}, "v6": {…}}. Eine Adresse bleibt nach dem letzten Erscheinen in der bunny-Liste noch
HALTETAGE erhalten – eine kurzzeitig unvollständige Antwort von bunny sperrt so keinen Edge-Server aus. Eine Antwort mit zu
wenigen gültigen Adressen (MIN_V4) oder mit vielen ungültigen Einträgen wird verworfen; die bisherige Liste bleibt.

Regelwerk (Tabelle inet stafl_netzsperre, eigene Tabelle neben den Regeln von Docker, atomar ersetzt): Neue Verbindungen über
die Schnittstelle IF an Port 80 oder 443 (TCP, UDP) – über die Docker-Weiterleitung (Haken forward, ursprünglicher Zielport)
und an Dienste des Hosts (Haken input, z. B. der Docker-Proxy für IPv6) – von Adressen außerhalb der Liste gehen in die
Kette „fremd“: Protokoll (höchstens 6 je Minute) und im Modus „an“ verwerfen. Alles andere (andere Schnittstellen, Antworten,
bestehende Verbindungen, andere Ports) bleibt unberührt.
"""
import datetime as dt
import ipaddress
import json
import os
import re
import sys
import tempfile
import urllib.request

QUELLE_V4 = "https://api.bunny.net/system/edgeserverlist"
QUELLE_V6 = "https://api.bunny.net/system/edgeserverlist/ipv6"
MIN_V4 = 100           # bunny hat Hunderte Edge-Server; weniger ist eine kaputte Antwort
MAX_EINTRAEGE = 100000
MAX_UNGUELTIG = 5
HALTETAGE = 14
TABELLE = "stafl_netzsperre"
PREFIX = "stafl-netzsperre: "
PORTS = "{ 80, 443 }"
SCHNITTSTELLE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")
# Nur für Tests (tests/deploy/test_cdn_netzsperre.*): WA_TESTNETZE=1 lässt zusätzlich die Dokumentationsnetze zu (RFC 5737,
# RFC 3849) – so braucht kein Test echte Adressen (GR-007). Auf dem Server nie gesetzt.
TESTNETZE = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")]


def erlaubt(a):
    if a.is_global:
        return True
    return os.environ.get("WA_TESTNETZE") == "1" and any(a in n for n in TESTNETZE if n.version == a.version)


def jetzt():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def zeit(text):
    try:
        return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def pruefe_liste(roh, familie):
    """Antwort von bunny (JSON-Liste) → sortierte gültige öffentliche Adressen der Familie 4 oder 6. ValueError bei kaputter Antwort."""
    try:
        daten = json.loads(roh)
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError("keine JSON-Liste") from e
    if not isinstance(daten, list):
        raise ValueError("keine JSON-Liste")
    if len(daten) > MAX_EINTRAEGE:
        raise ValueError("zu viele Einträge (%d)" % len(daten))
    gut, schlecht = set(), 0
    for e in daten:
        try:
            a = ipaddress.ip_address(str(e).strip())
        except ValueError:
            schlecht += 1
            continue
        if a.version != familie or not erlaubt(a):
            schlecht += 1
            continue
        gut.add(str(a))
    if schlecht > MAX_UNGUELTIG:
        raise ValueError("%d ungültige Einträge" % schlecht)
    if familie == 4 and len(gut) < MIN_V4:
        raise ValueError("nur %d gültige IPv4-Adressen (mindestens %d)" % (len(gut), MIN_V4))
    return sorted(gut, key=ipaddress.ip_address)


def zusammenfuehren(bisher, neu, t, haltetage=HALTETAGE):
    """bisher {Adresse: zuletzt gesehen} + neue Adressen → (Ergebnis, Anzahl neu, Anzahl entfallen)."""
    grenze = t - dt.timedelta(days=haltetage)
    erg = {}
    for a, gesehen in (bisher or {}).items():
        g = zeit(gesehen)
        if g is not None and g >= grenze:
            erg[a] = gesehen
    hinzu = sum(1 for a in neu if a not in erg)
    for a in neu:
        erg[a] = iso(t)
    entfallen = sum(1 for a in (bisher or {}) if a not in erg)
    return erg, hinzu, entfallen


def netze(adressen):
    """Adressen → zusammengefasste Netze (für die nft-Menge mit flags interval)."""
    nur = [ipaddress.ip_network(a) for a in adressen]
    return [str(n) for n in ipaddress.collapse_addresses(nur)]


def lesen(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def schreiben(pfad, d):
    ordner = os.path.dirname(os.path.abspath(pfad))
    fd, tmp = tempfile.mkstemp(prefix=".netzsperre-", dir=ordner)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, sort_keys=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, pfad)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def holen(url):
    anfrage = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "stafl-netzsperre"})
    with urllib.request.urlopen(anfrage, timeout=20) as antwort:   # nosec: feste Adresse von bunny (oder Testdatei)
        return antwort.read(20 * 1024 * 1024)


def nutzbar(d):
    return isinstance(d.get("v4"), dict) and len(d["v4"]) >= MIN_V4


def abrufen(pfad, quelle4=None, quelle6=None):
    quelle4 = quelle4 or os.environ.get("WA_BUNNY_V4") or QUELLE_V4
    quelle6 = quelle6 or os.environ.get("WA_BUNNY_V6") or QUELLE_V6
    d = lesen(pfad)
    t = jetzt()
    d["version"] = 1
    d["versuch"] = iso(t)
    try:
        v4 = pruefe_liste(holen(quelle4), 4)
    except Exception as e:   # Netz, HTTP, Inhalt: bisherige Liste bleibt
        d["fehler"] = "IPv4-Liste: %s" % (e if isinstance(e, ValueError) else type(e).__name__)
        schreiben(pfad, d)
        if nutzbar(d):
            print("bunny-Liste nicht aktualisiert (%s) – die bisherige bleibt (%d IPv4, Stand %s)."
                  % (d["fehler"], len(d["v4"]), d.get("abgerufen", "?")), file=sys.stderr)
            return 1
        print("bunny-Liste nicht abrufbar (%s) – keine nutzbare Liste vorhanden." % d["fehler"], file=sys.stderr)
        return 2
    fehler6 = None
    try:
        v6 = pruefe_liste(holen(quelle6), 6)
    except Exception as e:
        v6, fehler6 = None, "IPv6-Liste: %s" % (e if isinstance(e, ValueError) else type(e).__name__)
    d["v4"], neu4, weg4 = zusammenfuehren(d.get("v4"), v4, t)
    if v6 is not None:
        d["v6"], neu6, weg6 = zusammenfuehren(d.get("v6"), v6, t)
    else:
        d.setdefault("v6", {})
        neu6 = weg6 = 0
    d["abgerufen"] = iso(t)
    d["fehler"] = fehler6
    schreiben(pfad, d)
    print("bunny-Liste: %d IPv4, %d IPv6 (neu %d, nach %d Tagen entfallen %d)%s"
          % (len(d["v4"]), len(d["v6"]), neu4 + neu6, HALTETAGE, weg4 + weg6,
             " – " + fehler6 + ", bisherige IPv6-Liste bleibt" if fehler6 else ""))
    return 0


def faellig(pfad, stunden):
    d = lesen(pfad)
    t = zeit(d.get("abgerufen")) if nutzbar(d) else None
    return t is None or jetzt() - t >= dt.timedelta(hours=float(stunden))


def menge(name, typ, eintraege):
    zeilen = ["\tset %s {" % name, "\t\ttype %s" % typ, "\t\tflags interval"]
    if eintraege:
        stuecke = [", ".join(eintraege[i:i + 8]) for i in range(0, len(eintraege), 8)]
        zeilen.append("\t\telements = {\n\t\t\t" + ",\n\t\t\t".join(stuecke) + "\n\t\t}")
    zeilen.append("\t}")
    return "\n".join(zeilen)


def regelwerk(modus, schnittstelle, netze4, netze6):
    if modus not in ("beobachten", "an"):
        raise ValueError("Modus beobachten oder an")
    if not SCHNITTSTELLE.match(schnittstelle or ""):
        raise ValueError("ungültige Schnittstelle")
    if len(netze4) == 0:
        raise ValueError("leere IPv4-Liste")
    neu = 'iifname "%s" ct state new' % schnittstelle
    weiter = neu + " ct direction original meta l4proto { tcp, udp } ct original proto-dst " + PORTS
    ein = neu + " meta l4proto { tcp, udp } th dport " + PORTS
    return "\n".join([
        "# Erzeugt von deploy/cdn_netzsperre.py (deploy/cdn-netzsperre.sh) – nicht von Hand ändern. Modus: %s" % modus,
        "add table inet " + TABELLE,
        "delete table inet " + TABELLE,
        "table inet %s {" % TABELLE,
        menge("bunny4", "ipv4_addr", netze4),
        menge("bunny6", "ipv6_addr", netze6),
        "\tchain fremd {",
        '\t\tlimit rate 6/minute burst 12 packets log prefix "%s" level info' % PREFIX,
        "\t\tdrop" if modus == "an" else "\t\t# Modus beobachten: nur zählen und protokollieren",
        "\t}",
        "\tchain weiterleiten {",
        "\t\ttype filter hook forward priority filter - 10; policy accept;",
        "\t\t%s ip saddr != @bunny4 counter jump fremd" % weiter,
        "\t\t%s ip6 saddr != @bunny6 counter jump fremd" % weiter,
        "\t}",
        "\tchain eingang {",
        "\t\ttype filter hook input priority filter - 10; policy accept;",
        "\t\t%s ip saddr != @bunny4 counter jump fremd" % ein,
        "\t\t%s ip6 saddr != @bunny6 counter jump fremd" % ein,
        "\t}",
        "}",
        "",
    ])


def regelwerk_aus_liste(pfad, modus, schnittstelle):
    d = lesen(pfad)
    if not nutzbar(d):
        raise ValueError("keine nutzbare bunny-Liste (%s)" % pfad)
    return regelwerk(modus, schnittstelle, netze(d["v4"]), netze(d.get("v6") or {}))


def bericht(pfad, zeilen):
    d = lesen(pfad)
    v4, v6 = d.get("v4") or {}, d.get("v6") or {}
    aus = ["bunny-Liste: %d IPv4, %d IPv6, abgerufen %s%s" % (
        len(v4), len(v6), d.get("abgerufen", "nie"), (" – letzter Fehler: " + d["fehler"]) if d.get("fehler") else "")]
    zaehler = {}
    for z in zeilen:
        if PREFIX.strip() not in z:
            continue
        m = re.search(r"\bSRC=([0-9A-Fa-f:.]+)", z)
        p = re.search(r"\bDPT=(\d+)", z)
        if m:
            schluessel = (m.group(1), p.group(1) if p else "?")
            zaehler[schluessel] = zaehler.get(schluessel, 0) + 1
    if not zaehler:
        aus.append("Fremde Verbindungsversuche im Protokoll: keine")
        return "\n".join(aus)
    aus.append("Fremde Verbindungsversuche im Protokoll (höchstens 6 je Minute protokolliert): %d von %d Adressen"
               % (sum(zaehler.values()), len({a for a, _ in zaehler})))
    jetzt_in_liste = 0
    for (adresse, port), n in sorted(zaehler.items(), key=lambda x: (-x[1], x[0]))[:10]:
        try:
            normal = str(ipaddress.ip_address(adresse))
        except ValueError:
            normal = adresse
        drin = normal in v4 or normal in v6
        jetzt_in_liste += drin
        aus.append("  %6d  %-40s Port %s%s" % (n, normal, port, "  ← inzwischen in der bunny-Liste" if drin else ""))
    if jetzt_in_liste:
        aus.append("Hinweis: Adressen mit „inzwischen in der bunny-Liste“ waren Edge-Server von bunny – die Liste ist jetzt aktuell.")
    return "\n".join(aus)


def main(argv):
    if len(argv) >= 2 and argv[0] == "abrufen":
        return abrufen(argv[1])
    if len(argv) == 3 and argv[0] == "faellig":
        return 0 if faellig(argv[1], argv[2]) else 1
    if len(argv) == 4 and argv[0] == "regelwerk":
        try:
            sys.stdout.write(regelwerk_aus_liste(argv[1], argv[2], argv[3]))
        except ValueError as e:
            print("Kein Regelwerk: %s" % e, file=sys.stderr)
            return 2
        return 0
    if len(argv) == 2 and argv[0] == "bericht":
        print(bericht(argv[1], sys.stdin.read().splitlines()))
        return 0
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
