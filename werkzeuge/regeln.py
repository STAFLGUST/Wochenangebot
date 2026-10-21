#!/usr/bin/env python3
"""Regelwerk der STAFL-Plattform prüfen und Änderungsfolgen ermitteln (nur Python-Standardbibliothek).

  python3 werkzeuge/regeln.py pruefen                   Alle Prüfungen (CI); Ausgang 1 bei Fehlern
  python3 werkzeuge/regeln.py betroffen [DATEI …]       Welche Module, Regeln, Daten und Tests betrifft eine Änderung?
  python3 werkzeuge/regeln.py betroffen --basis origin/main   … für alle Änderungen gegenüber main (auch ungespeicherte)
  python3 werkzeuge/regeln.py modul <id>                Steckbrief eines Moduls (Pfade, Daten, Rechte, Regeln, Tests)
  python3 werkzeuge/regeln.py erzeugen                  erzeugte PHP-Listen schreiben: app/api/lib/aktionen-liste.php
                                                        (regeln/aktionen/) und app/api/lib/module-liste.php (Modulregister,
                                                        Entscheidungstabelle aus regeln/module.toml und regeln/wartung.toml)

Quelle aller Angaben: regeln/*.toml. Erklärung: docs/plattform/multi-agent.md
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

ENTWICKLUNG = ["geplant", "in_entwicklung", "in_pruefung", "fertig"]
FREIGABE = ["keine", "test", "produktiv", "deaktiviert"]
SCHUTZ = ["oeffentlich", "intern", "vertraulich", "geheim"]
ID_MUSTER = re.compile(r"^[a-z][a-z0-9_]*$")
GR_MUSTER = re.compile(r"\bGR-\d{3}\b")
DASHBOARD_DOMAIN = "dashboard-stafl.de"

# Speicherzugriffe im PHP-Code: store_write('name' …), with_lock('name' …), store_read('prefix/' . $x) …
SCHREIB_RE = re.compile(r"\b(store_write|store_delete|with_lock)\(\s*'([A-Za-z0-9_\-/]+)'(\s*\.)?")
LESE_RE = re.compile(r"\b(store_read|store_mtime|store_names)\(\s*'([A-Za-z0-9_\-/]+)'(\s*\.)?")
PERMS_RE = re.compile(r"^\s*'([a-z][a-z0-9_.]*)'\s*=>\s*\[", re.MULTILINE)
SUITE_RE = re.compile(r"^\s*'([a-z0-9_]+)':\s*\(|^SUITES\['([a-z0-9_]+)'\]\s*=", re.MULTILINE)


# ─────────────────────────────── Laden ───────────────────────────────

@dataclass
class Regelwerk:
    wurzel: Path
    module: dict
    daten: dict
    rechte: dict
    katalog: dict
    wartung: dict
    aktionen: dict = field(default_factory=dict)   # Dateiname (Modul) → Inhalt von regeln/aktionen/<modul>.toml
    fehler: list = field(default_factory=list)
    warnungen: list = field(default_factory=list)

    @property
    def modulliste(self) -> list:
        return self.module.get("modul", [])

    def modul(self, mid: str) -> dict | None:
        return next((m for m in self.modulliste if m.get("id") == mid), None)

    def modul_ids(self) -> set:
        return {m.get("id") for m in self.modulliste}

    def f(self, text: str) -> None:
        self.fehler.append(text)

    def w(self, text: str) -> None:
        self.warnungen.append(text)


def laden(wurzel: Path = WURZEL) -> Regelwerk:
    def toml(name: str) -> dict:
        pfad = wurzel / "regeln" / name
        try:
            return tomllib.loads(pfad.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SystemExit(f"FEHLER: {pfad.relative_to(wurzel)} fehlt")
        except tomllib.TOMLDecodeError as e:
            raise SystemExit(f"FEHLER: {pfad.relative_to(wurzel)} ist kein gültiges TOML: {e}")
    rw = Regelwerk(wurzel, toml("module.toml"), toml("datenverantwortung.toml"), toml("berechtigungen.toml"),
                   toml("katalog.toml"), toml("wartung.toml"))
    ordner = wurzel / "regeln" / "aktionen"
    for pfad in sorted(ordner.glob("*.toml")) if ordner.is_dir() else []:
        rw.aktionen[pfad.stem] = toml(f"aktionen/{pfad.name}")
    for name, d in [("module.toml", rw.module), ("datenverantwortung.toml", rw.daten),
                    ("berechtigungen.toml", rw.rechte), ("katalog.toml", rw.katalog), ("wartung.toml", rw.wartung)]:
        if d.get("schema") != 1:
            rw.f(f"regeln/{name}: unbekannte oder fehlende Angabe schema (erwartet 1)")
    return rw


# ─────────────────────────────── Dateien und Pfadmuster ───────────────────────────────

def dateien(wurzel: Path) -> list:
    """Versionierte Dateien (git ls-files); ohne Git: alle Dateien außer .git und Arbeitsordnern."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=wurzel,
                             capture_output=True, check=True)
        liste = [p for p in out.stdout.decode().split("\0") if p]
        return sorted(p for p in liste if (wurzel / p).is_file())
    except (OSError, subprocess.CalledProcessError):
        aus = {".git", "node_modules", "__pycache__", ".arbeit", ".ergebnisse"}
        return sorted(str(p.relative_to(wurzel)).replace("\\", "/") for p in wurzel.rglob("*")
                      if p.is_file() and not (set(p.relative_to(wurzel).parts) & aus))


_muster_cache: dict = {}


def muster_regex(muster: str) -> re.Pattern:
    if muster not in _muster_cache:
        teile = re.split(r"(\*\*|\*)", muster)
        rx = "".join(".*" if t == "**" else "[^/]*" if t == "*" else re.escape(t) for t in teile)
        _muster_cache[muster] = re.compile(rx + r"\Z")
    return _muster_cache[muster]


def passt(muster: str, pfad: str) -> bool:
    return bool(muster_regex(muster).match(pfad))


def genauigkeit(muster: str) -> tuple:
    """Exakte Pfade schlagen Muster; sonst gewinnt das längere Muster ohne Platzhalter."""
    return (0 if "*" in muster else 1, len(muster.replace("*", "")))


def eigentuemer(rw: Regelwerk, pfad: str, geplant: bool = True) -> tuple:
    """(modul_id, muster) des genauesten passenden Musters; bei Gleichstand verschiedener Module: Fehlerhinweis."""
    treffer = []
    for m in rw.modulliste:
        quellen = list(m.get("pfade", [])) + (list(m.get("pfade_geplant", [])) if geplant else [])
        for mu in quellen:
            if passt(mu, pfad):
                treffer.append((genauigkeit(mu), m["id"], mu))
    if not treffer:
        return None, None
    treffer.sort(reverse=True)
    beste = [t for t in treffer if t[0] == treffer[0][0]]
    if len({t[1] for t in beste}) > 1:
        return "!mehrdeutig", " / ".join(f"{t[1]}:{t[2]}" for t in beste)
    return treffer[0][1], treffer[0][2]


def koordination(rw: Regelwerk, pfad: str) -> list:
    return [k["bereich"] for k in rw.module.get("koordination", []) if any(passt(mu, pfad) for mu in k.get("pfade", []))]


# ─────────────────────────────── Code lesen ───────────────────────────────

def dokumentname(name: str, folgt_verkettung: bool, ist_names: bool = False) -> str:
    if folgt_verkettung or name.endswith("/") or ist_names:
        return name.rstrip("/") + "/*"
    return name


def speicherzugriffe(wurzel: Path, liste: list) -> dict:
    """Pfad → {'schreibt': set, 'liest': set} für PHP-Dateien unter app/ und deploy/."""
    erg = {}
    for p in liste:
        if not p.endswith(".php") or not (p.startswith("app/") or p.startswith("deploy/")) or "/geo/" in p:
            continue
        text = (wurzel / p).read_text(encoding="utf-8", errors="ignore")
        s = {dokumentname(m.group(2), bool(m.group(3))) for m in SCHREIB_RE.finditer(text)}
        l = {dokumentname(m.group(2), bool(m.group(3)), m.group(1) == "store_names") for m in LESE_RE.finditer(text)}
        if s or l:
            erg[p] = {"schreibt": s, "liest": l - s}
    return erg


def dokument_eintrag(rw: Regelwerk, name: str) -> dict | None:
    for d in rw.daten.get("dokument", []):
        if d.get("name") == name:
            return d
    # Sperrname „x“ gehört zu Dokument „x/*“ (z. B. with_lock('protokoll') für protokoll/*)
    for d in rw.daten.get("dokument", []):
        if d.get("name") == name + "/*":
            return d
    return None


def perms_aus_code(wurzel: Path) -> list:
    pfad = wurzel / "app/api/lib/rechte.php"
    if not pfad.is_file():
        return []
    text = pfad.read_text(encoding="utf-8")
    block = re.search(r"const PERMS = \[(.*?)\n\];", text, re.DOTALL)
    return PERMS_RE.findall(block.group(1)) if block else []


def testgruppen_aus_code(wurzel: Path) -> set:
    pfad = wurzel / "tests/run_e2e.py"
    if not pfad.is_file():
        return set()
    return {a or b for a, b in SUITE_RE.findall(pfad.read_text(encoding="utf-8"))}


def ci_schritte(wurzel: Path) -> set:
    pfad = wurzel / ".github/workflows/ci.yml"
    if not pfad.is_file():
        return set()
    return {m.strip().strip('"') for m in re.findall(r"^\s*-?\s*name:\s*(.+)$", pfad.read_text(encoding="utf-8"), re.MULTILINE)}


def caddy_hosts(wurzel: Path) -> tuple:
    """(alle Hosts der dashboard-Domain, Hosts im 503-Platzhalterblock)"""
    pfad = wurzel / "Caddyfile"
    if not pfad.is_file():
        return set(), set()
    text = pfad.read_text(encoding="utf-8")
    alle, platzhalter = set(), set()
    for m in re.finditer(r"^([^\s#{][^{\n]*)\{\n(.*?)^\}", text, re.MULTILINE | re.DOTALL):
        hosts = {h.strip() for h in m.group(1).split(",") if DASHBOARD_DOMAIN in h}
        alle |= hosts
        if hosts and re.search(r'^\s*respond\s+"[^"]*"\s+503\s*$', m.group(2), re.MULTILINE) \
                and "reverse_proxy" not in m.group(2):
            platzhalter |= hosts
    return alle, platzhalter


def host(adresse: str) -> str:
    return re.sub(r"^https://([^/]+).*$", r"\1", adresse)


# ─────────────────────────────── Zustandsmodell ───────────────────────────────

def freigabe_zulaessig(wartung: dict, entwicklung: str, freigabe: str) -> bool:
    return freigabe in wartung.get("freigabe_erlaubt", {}).get(entwicklung, [])


def entscheiden(wartung: dict, lage: dict) -> dict | None:
    """Erste passende Zeile der Entscheidungstabelle (regeln/wartung.toml, [[regel]])."""
    for r in sorted(wartung.get("regel", []), key=lambda r: r.get("nr", 0)):
        bed = dict(r.get("wenn", {}))
        unz = bed.pop("freigabe_unzulaessig", None)
        if unz is not None and unz != (not freigabe_zulaessig(wartung, lage["entwicklung"], lage["freigabe"])):
            continue
        if all(lage.get(k) == v for k, v in bed.items()):
            return r
    return None


def alle_lagen(wartung: dict):
    w = wartung.get("werte", {})
    for e, fr, b, p in itertools.product(w.get("entwicklung", []), w.get("freigabe", []), w.get("betrieb", []),
                                         w.get("person", [])):
        yield {"entwicklung": e, "freigabe": fr, "betrieb": b, "person": p}


# ─────────────────────────────── Prüfungen ───────────────────────────────

def pruefe_module(rw: Regelwerk) -> None:
    ids = []
    reihen = {}
    for m in rw.modulliste:
        mid = m.get("id", "?")
        ids.append(mid)
        if not ID_MUSTER.match(str(mid)):
            rw.f(f"Modul „{mid}“: ungültige ID (klein, a-z, 0-9, _)")
        for feld in ("name", "beschreibung", "icon", "agent"):
            if not m.get(feld):
                rw.f(f"Modul {mid}: Feld „{feld}“ fehlt")
        for feld in ("abhaengigkeiten", "testgruppen", "pfade", "pfade_geplant"):
            if not isinstance(m.get(feld), list):
                rw.f(f"Modul {mid}: Feld „{feld}“ fehlt oder ist keine Liste")
        if m.get("dashboard"):
            r = m.get("reihenfolge")
            if not isinstance(r, int):
                rw.f(f"Modul {mid}: Dashboard-Modul ohne ganzzahlige „reihenfolge“")
            elif r in reihen:
                rw.f(f"Modul {mid}: reihenfolge {r} schon bei {reihen[r]}")
            else:
                reihen[r] = mid
        teil = m.get("teil_von")
        if teil:
            if m.get("pfade") or m.get("pfade_geplant") or m.get("oberflaeche"):
                rw.f(f"Modul {mid} ist Teil von {teil}: keine eigenen Pfade/Oberflächen (sonst doppelte Implementierung)")
            if any(d.get("eigentuemer") == mid for d in rw.daten.get("dokument", [])):
                rw.f(f"Modul {mid} ist Teil von {teil}: darf keine eigenen Dokumente besitzen")
        ob_ids = set()
        for o in m.get("oberflaeche", []):
            oid = f"{mid}.{o.get('id')}"
            if o.get("id") in ob_ids:
                rw.f(f"Oberfläche {oid} doppelt")
            ob_ids.add(o.get("id"))
            if o.get("art") not in ("intern", "extern"):
                rw.f(f"Oberfläche {oid}: art muss intern oder extern sein")
            if not str(o.get("adresse", "")).startswith("https://"):
                rw.f(f"Oberfläche {oid}: adresse muss mit https:// beginnen")
            if "ziel" in o and not str(o["ziel"]).startswith("https://"):
                rw.f(f"Oberfläche {oid}: ziel muss mit https:// beginnen")
            if o.get("dns") is False and o.get("freigabe") != "keine":
                rw.f(f"Oberfläche {oid}: ohne DNS-Eintrag (dns = false) ist nur freigabe = \"keine\" zulässig")
            e, fr = o.get("entwicklung"), o.get("freigabe")
            if e not in ENTWICKLUNG:
                rw.f(f"Oberfläche {oid}: unbekannter Entwicklungsstand „{e}“ ({', '.join(ENTWICKLUNG)})")
            if fr not in FREIGABE:
                rw.f(f"Oberfläche {oid}: unbekannte Freigabe „{fr}“ ({', '.join(FREIGABE)})")
            if e in ENTWICKLUNG and fr in FREIGABE and not freigabe_zulaessig(rw.wartung, e, fr):
                rw.f(f"Oberfläche {oid}: Freigabe „{fr}“ ist bei Entwicklungsstand „{e}“ nicht zulässig (GR-102)")
            if not isinstance(o.get("sperrbar"), bool):
                rw.f(f"Oberfläche {oid}: sperrbar (true/false) fehlt")
            for feld in ("adresse", "ziel"):
                if o.get("art") == "extern" and DASHBOARD_DOMAIN in host(str(o.get(feld, ""))):
                    rw.f(f"Oberfläche {oid}: externe Oberflächen dürfen nicht unter {DASHBOARD_DOMAIN} liegen (GR-104)")
        if m.get("dashboard"):
            ziel = m.get("kachel_ziel")
            if ziel:
                zm, _, zo = ziel.rpartition(".") if "." in ziel else (mid, ".", ziel)
                zmod = rw.modul(zm or mid)
                if not zmod or not any(o.get("id") == zo for o in zmod.get("oberflaeche", [])):
                    rw.f(f"Modul {mid}: kachel_ziel „{ziel}“ verweist auf keine Oberfläche")
            elif not any(o.get("art") == "intern" for o in m.get("oberflaeche", [])):
                rw.f(f"Modul {mid}: Dashboard-Modul braucht eine interne Oberfläche oder ein kachel_ziel")
    doppelt = {i for i in ids if ids.count(i) > 1}
    for i in sorted(doppelt):
        rw.f(f"Modul-ID „{i}“ mehrfach vergeben")
    bekannt = set(ids)
    for m in rw.modulliste:
        for a in m.get("abhaengigkeiten", []):
            if a not in bekannt:
                rw.f(f"Modul {m.get('id')}: unbekannte Abhängigkeit „{a}“")
        if m.get("teil_von") and m["teil_von"] not in bekannt:
            rw.f(f"Modul {m.get('id')}: teil_von „{m['teil_von']}“ unbekannt")
    # Abhängigkeiten ohne Kreis
    graph = {m.get("id"): set(m.get("abhaengigkeiten", [])) for m in rw.modulliste}
    besucht, aktiv = set(), set()

    def tief(n, weg):
        if n in aktiv:
            rw.f("Kreis in den Modulabhängigkeiten: " + " → ".join(weg + [n]))
            return
        if n in besucht or n not in graph:
            return
        aktiv.add(n)
        for k in sorted(graph[n]):
            tief(k, weg + [n])
        aktiv.discard(n)
        besucht.add(n)
    for n in sorted(graph):
        tief(n, [])
    for p in rw.module.get("dashboard", {}).get("pflichtmodule", []):
        m = rw.modul(p)
        if not m or not m.get("dashboard"):
            rw.f(f"Pflichtmodul „{p}“ fehlt im Dashboard (regeln/module.toml)")
    # Schutz vor Aussperrung: Dashboard-Start und Verwaltung → System nie sperrbar
    for ziel in ("dashboard.start", "verwaltung.system"):
        mid, oid = ziel.split(".")
        m = rw.modul(mid)
        o = next((o for o in (m or {}).get("oberflaeche", []) if o.get("id") == oid), None)
        if not o:
            rw.f(f"Oberfläche {ziel} fehlt (Schutz vor Aussperrung, regeln/wartung.toml [notfall])")
        elif o.get("sperrbar") is not False:
            rw.f(f"Oberfläche {ziel} muss sperrbar = false haben (Schutz vor Aussperrung)")


def pruefe_pfade(rw: Regelwerk, liste: list) -> None:
    for p in liste:
        mid, mu = eigentuemer(rw, p)
        if mid is None:
            rw.f(f"Datei ohne Eigentümer: {p} – in regeln/module.toml einem Modul zuordnen")
        elif mid == "!mehrdeutig":
            rw.f(f"Datei {p} ist mehrdeutig zugeordnet ({mu}) – genaueres Muster angeben")
    for m in rw.modulliste:
        for mu in m.get("pfade", []):
            if not any(passt(mu, p) for p in liste):
                rw.f(f"Modul {m['id']}: Pfad „{mu}“ passt auf keine Datei (falls noch geplant: nach pfade_geplant)")
    for k in rw.module.get("koordination", []):
        for mu in k.get("pfade", []):
            if not any(passt(mu, p) for p in liste):
                rw.f(f"Koordination „{k.get('bereich')}“: Pfad „{mu}“ passt auf keine Datei")


def pruefe_daten(rw: Regelwerk, liste: list) -> None:
    ids = rw.modul_ids()
    namen = []
    for d in rw.daten.get("dokument", []):
        n = d.get("name", "?")
        namen.append(n)
        if d.get("eigentuemer") not in ids:
            rw.f(f"Dokument {n}: unbekannter Eigentümer „{d.get('eigentuemer')}“")
        if d.get("schutz") not in SCHUTZ:
            rw.f(f"Dokument {n}: schutz muss eines von {', '.join(SCHUTZ)} sein")
        if not d.get("beschreibung"):
            rw.f(f"Dokument {n}: beschreibung fehlt")
        for feld in ("leser", "schreiber"):
            for x in d.get(feld, []):
                if x not in ids:
                    rw.f(f"Dokument {n}: unbekanntes Modul „{x}“ in {feld}")
                if x == d.get("eigentuemer"):
                    rw.f(f"Dokument {n}: Eigentümer {x} steht unnötig in {feld}")
    for n in sorted({n for n in namen if namen.count(n) > 1}):
        rw.f(f"Dokument „{n}“ mehrfach registriert")

    zugriffe = speicherzugriffe(rw.wurzel, liste)
    gefunden = set()
    for pfad, z in sorted(zugriffe.items()):
        mod, _ = eigentuemer(rw, pfad)
        for art, docs in (("schreibt", z["schreibt"]), ("liest", z["liest"])):
            for doc in sorted(docs):
                e = dokument_eintrag(rw, doc)
                if not e:
                    rw.f(f"{pfad} {art} Dokument „{doc}“, das nicht in regeln/datenverantwortung.toml steht (GR-101)")
                    continue
                gefunden.add(e["name"])
                if e.get("geplant"):
                    rw.f(f"Dokument {e['name']} ist als geplant markiert, wird aber schon verwendet ({pfad}) – Vermerk entfernen")
                eig = e.get("eigentuemer")
                if mod == eig:
                    continue
                if art == "schreibt" and mod not in e.get("schreiber", []):
                    rw.f(f"{pfad} (Modul {mod}) schreibt „{e['name']}“ von {eig} ohne Eintrag unter schreiber (GR-101)")
                if art == "liest" and mod != "plattform" and mod not in e.get("leser", []) + e.get("schreiber", []):
                    rw.f(f"{pfad} (Modul {mod}) liest „{e['name']}“ von {eig} ohne Eintrag unter leser (GR-101)")
    for d in rw.daten.get("dokument", []):
        if d["name"] not in gefunden and not d.get("dynamisch") and not d.get("geplant"):
            rw.f(f"Dokument {d['name']} wird im Code nicht (mehr) verwendet – entfernen oder dynamisch/geplant markieren")


def pruefe_rechte(rw: Regelwerk) -> None:
    ids = rw.modul_ids()
    perms = perms_aus_code(rw.wurzel)
    if not perms:
        rw.f("Rechtekatalog PERMS in app/api/lib/rechte.php nicht gefunden")
    zu = rw.rechte.get("zuordnung", {})
    for p in perms:
        if p in zu:
            if zu[p] not in ids:
                rw.f(f"Recht {p}: unbekanntes Modul „{zu[p]}“")
        elif p.split(".")[0] not in ids:
            rw.f(f"Recht {p} ist keinem Modul zugeordnet – Präfix <modul>. verwenden oder in regeln/berechtigungen.toml eintragen (GR-103)")
    for p in zu:
        if p not in perms:
            rw.f(f"regeln/berechtigungen.toml: Recht {p} gibt es in rechte.php nicht (mehr)")
    na = rw.rechte.get("nur_administratoren", {})
    if na and na.get("modul") not in ids:
        rw.f("regeln/berechtigungen.toml: [nur_administratoren] verweist auf ein unbekanntes Modul")


def test_verweis_ok(rw: Regelwerk, t: str, gruppen: set, schritte: set) -> str | None:
    art, _, wert = t.partition(":")
    if art == "e2e":
        return None if wert in gruppen else f"E2E-Gruppe „{wert}“ gibt es nicht (tests/run_e2e.py)"
    if art == "datei":
        return None if (rw.wurzel / wert).is_file() else f"Testdatei {wert} fehlt"
    if art == "ci":
        return None if wert in schritte else f"CI-Schritt „{wert}“ gibt es nicht (.github/workflows/ci.yml)"
    return f"Testverweis „{t}“: erlaubt sind e2e:, datei:, ci:"


def pruefe_tests(rw: Regelwerk) -> None:
    gruppen = testgruppen_aus_code(rw.wurzel)
    zugeordnet = set()
    for m in rw.modulliste:
        for g in m.get("testgruppen", []):
            zugeordnet.add(g)
            if g not in gruppen:
                rw.f(f"Modul {m['id']}: E2E-Gruppe „{g}“ gibt es nicht (tests/run_e2e.py)")
    for g in sorted(gruppen - zugeordnet):
        rw.f(f"E2E-Gruppe „{g}“ ist keinem Modul zugeordnet (testgruppen in regeln/module.toml)")


def pruefe_katalog(rw: Regelwerk) -> None:
    ids = rw.modul_ids()
    gruppen = testgruppen_aus_code(rw.wurzel)
    schritte = ci_schritte(rw.wurzel)
    kennungen = []
    for r in rw.katalog.get("regel", []):
        rid = r.get("id", "?")
        kennungen.append(rid)
        if not re.fullmatch(r"GR-\d{3}", str(rid)):
            rw.f(f"Regel „{rid}“: Kennung muss GR-123 lauten")
        for feld in ("titel", "beschreibung", "verantwortlich", "seit"):
            if not r.get(feld):
                rw.f(f"Regel {rid}: Feld „{feld}“ fehlt")
        if not isinstance(r.get("version"), int) or r.get("version", 0) < 1:
            rw.f(f"Regel {rid}: version muss eine Zahl ≥ 1 sein")
        if r.get("verantwortlich") not in ids:
            rw.f(f"Regel {rid}: verantwortlich „{r.get('verantwortlich')}“ ist kein Modul")
        for mod in r.get("module", []):
            if mod not in ids:
                rw.f(f"Regel {rid}: unbekanntes Modul „{mod}“")
        for doc in r.get("daten", []):
            if not dokument_eintrag(rw, doc):
                rw.f(f"Regel {rid}: Dokument „{doc}“ nicht registriert")
        status = r.get("status")
        if status not in ("verbindlich", "geplant"):
            rw.f(f"Regel {rid}: status muss verbindlich oder geplant sein")
        if status == "verbindlich" and not r.get("tests"):
            rw.f(f"Regel {rid}: verbindliche Regel ohne Tests")
        if status == "geplant" and not r.get("phase"):
            rw.f(f"Regel {rid}: geplante Regel braucht die Phase, in der sie durchgesetzt wird")
        for t in r.get("tests", []):
            fehler = test_verweis_ok(rw, t, gruppen, schritte)
            if fehler:
                rw.f(f"Regel {rid}: {fehler}")
    for k in sorted({k for k in kennungen if kennungen.count(k) > 1}):
        rw.f(f"Regel {k} mehrfach vergeben")
    agents = rw.wurzel / "AGENTS.md"
    genannt = set(GR_MUSTER.findall(agents.read_text(encoding="utf-8"))) if agents.is_file() else set()
    for k in sorted(genannt - set(kennungen)):
        rw.f(f"AGENTS.md nennt {k}, das in regeln/katalog.toml fehlt")
    for r in rw.katalog.get("regel", []):
        if r.get("quelle") == "AGENTS.md" and r.get("id") not in genannt:
            rw.f(f"Regel {r.get('id')} (quelle AGENTS.md) wird in AGENTS.md nicht genannt")


def pruefe_wartung(rw: Regelwerk) -> None:
    w = rw.wartung
    werte = w.get("werte", {})
    if werte.get("entwicklung") != ENTWICKLUNG or werte.get("freigabe") != FREIGABE:
        rw.f("regeln/wartung.toml: [werte] entwicklung/freigabe passen nicht zum Prüfwerkzeug")
    for e in werte.get("entwicklung", []):
        for fr in w.get("freigabe_erlaubt", {}).get(e, []):
            if fr not in werte.get("freigabe", []):
                rw.f(f"regeln/wartung.toml: freigabe_erlaubt.{e} enthält unbekannte Freigabe „{fr}“")
    if set(w.get("freigabe_erlaubt", {})) != set(werte.get("entwicklung", [])):
        rw.f("regeln/wartung.toml: freigabe_erlaubt muss jeden Entwicklungsstand genau einmal nennen")
    if any(fr in ("test", "produktiv") for fr in w.get("freigabe_erlaubt", {}).get("geplant", [])):
        rw.f("regeln/wartung.toml: geplanter Code darf nie test/produktiv freigegeben werden")
    if "produktiv" in w.get("freigabe_erlaubt", {}).get("in_pruefung", []) + w.get("freigabe_erlaubt", {}).get("in_entwicklung", []):
        rw.f("regeln/wartung.toml: produktiv nur bei Entwicklungsstand fertig")
    erlaubt_wenn = {"entwicklung", "freigabe", "betrieb", "person", "freigabe_unzulaessig"}
    nummern = []
    for r in w.get("regel", []):
        nummern.append(r.get("nr"))
        for k, v in r.get("wenn", {}).items():
            if k not in erlaubt_wenn:
                rw.f(f"Wartungsregel {r.get('nr')}: unbekannte Bedingung „{k}“")
            elif k != "freigabe_unzulaessig" and v not in werte.get(k, []):
                rw.f(f"Wartungsregel {r.get('nr')}: unbekannter Wert {k} = „{v}“")
        if not isinstance(r.get("zugang"), bool) or r.get("http") not in (200, 403, 404, 503) or not r.get("kachel"):
            rw.f(f"Wartungsregel {r.get('nr')}: zugang (bool), http (200/403/404/503) und kachel sind Pflicht")
        if r.get("zugang") is True and r.get("http") != 200 or r.get("zugang") is False and r.get("http") == 200:
            rw.f(f"Wartungsregel {r.get('nr')}: zugang und http widersprechen sich")
    if len(set(nummern)) != len(nummern):
        rw.f("regeln/wartung.toml: Regelnummern doppelt")
    for lage in alle_lagen(w):
        r = entscheiden(w, lage)
        if r is None:
            rw.f(f"Entscheidungstabelle unvollständig: keine Regel für {lage}")
            continue
        for inv in w.get("invariante", []):
            if all(lage.get(k) == v for k, v in inv.get("wenn", {}).items()):
                for k, v in inv.get("dann", {}).items():
                    if r.get(k) != v:
                        rw.f(f"Invariante „{inv.get('name')}“ verletzt bei {lage}: Regel {r.get('nr')} ergibt {k} = {r.get(k)}")
    for t in w.get("testfall", []):
        r = entscheiden(w, t.get("eingabe", {}))
        if r is None:
            rw.f(f"Testfall „{t.get('name')}“: keine Regel passt")
            continue
        for k, v in t.get("erwartet", {}).items():
            if r.get(k) != v:
                rw.f(f"Testfall „{t.get('name')}“: erwartet {k} = {v}, Regel {r.get('nr')} ergibt {r.get(k)}")
    if len(w.get("testfall", [])) < 5:
        rw.f("regeln/wartung.toml: mindestens 5 Testfälle (Vertragstests) erforderlich")


def pruefe_caddy(rw: Regelwerk) -> None:
    alle, platzhalter = caddy_hosts(rw.wurzel)
    oberflaechen, ohne_dns, ziele = {}, set(), set()
    for m in rw.modulliste:
        for o in m.get("oberflaeche", []):
            h = host(o.get("adresse", ""))
            if o.get("ziel"):
                ziele.add(host(o["ziel"]))
            if DASHBOARD_DOMAIN in h:
                oberflaechen.setdefault(h, []).append((f"{m['id']}.{o.get('id')}", o.get("freigabe")))
                if o.get("dns") is False:
                    ohne_dns.add(h)
    umgebungen = {host(a) for u in rw.module.get("umgebung", []) for a in u.get("adressen", [])}
    for h in sorted(oberflaechen):
        if h in ohne_dns:
            if h in alle:
                rw.f(f"{h} steht im Caddyfile, ist aber als dns = false vermerkt – Vermerk entfernen, sobald DNS steht")
            continue
        if h not in alle:
            rw.f(f"{h} (Oberfläche {', '.join(o for o, _ in oberflaechen[h])}) fehlt im Caddyfile")
        if all(fr in ("keine", "deaktiviert") for _, fr in oberflaechen[h]) and h not in platzhalter:
            rw.f(f"{h}: keine Oberfläche freigegeben, Caddy muss den 503-Platzhalter liefern (GR-105)")
    for h in sorted(alle):
        if h.startswith("www."):
            continue
        if h not in oberflaechen and h not in umgebungen and h not in ziele:
            rw.f(f"Caddyfile: {h} ist weder Oberfläche noch Umgebung in regeln/module.toml")


# ─────────────────────────────── Aktionsregister ───────────────────────────────

AKTIONEN_LISTE = "app/api/lib/aktionen-liste.php"
# Schreibende Aktionen, die auch während einer Wartung erreichbar sein müssen: Anmeldung, Abmelden und der eigene Zugang
# (Pflicht-Passwortwechsel, Zwei-Faktor/Passkey bei der Anmeldung) – sonst könnten sich Administratoren nicht anmelden.
WARTUNG_FREI_SCHREIBEND = {"login", "login_2fa", "logout", "setup", "passkey_login_begin", "passkey_login", "change_password",
                           "twofa_begin", "twofa_enable", "passkey_begin", "passkey_register"}
CASE_RE = re.compile(r"case '([a-z0-9_]+)'")
GLEICH_RE = re.compile(r"\$action === '([a-z0-9_]+)'")


def aktionen_im_code(wurzel: Path) -> set:
    """Aktionen, die der Server tatsächlich bearbeitet: switch-Zweige in app/api/aktionen/*.php, Vergleiche mit
    $action dort sowie die Listen in orders_action() (app/api/orders.php)."""
    gefunden = set()
    ordner = wurzel / "app/api/aktionen"
    for p in sorted(ordner.glob("*.php")) if ordner.is_dir() else []:
        t = p.read_text(encoding="utf-8")
        gefunden |= set(CASE_RE.findall(t)) | set(GLEICH_RE.findall(t))
    orders = wurzel / "app/api/orders.php"
    if orders.is_file():
        m = re.search(r"function orders_action\(.*?\n\}", orders.read_text(encoding="utf-8"), re.DOTALL)
        if m:
            for liste in re.findall(r"in_array\(\$action, \[(.*?)\]", m.group(0)):
                gefunden |= set(re.findall(r"'([a-z0-9_]+)'", liste))
    return gefunden


def aktionen_tabelle(rw: Regelwerk) -> dict:
    """Aktion → Eigenschaften mit Standardwerten; doppelte Einträge meldet pruefe_aktionen."""
    tab = {}
    for datei, inhalt in sorted(rw.aktionen.items()):
        for name, a in sorted((inhalt.get("aktion") or {}).items()):
            if name in tab:
                continue
            tab[name] = {"modul": inhalt.get("modul", datei), "oberflaeche": a.get("oberflaeche", ""),
                         "schreibend": a.get("schreibend", False), "oeffentlich": a.get("oeffentlich", False),
                         "kunden_wartung": a.get("kunden_wartung", False), "wartung_frei": a.get("wartung_frei", False)}
    return tab


def php_wert(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def aktionen_php(rw: Regelwerk) -> str:
    z = ["<?php", "declare(strict_types=1);",
         "/* ERZEUGT von `python3 werkzeuge/regeln.py erzeugen` aus regeln/aktionen/*.toml – nicht von Hand ändern.",
         "   Je Aktion: zuständiges Modul, Oberfläche (Host), schreibend (true | false | 'post' = nur per POST),",
         "   öffentlich (ohne Mitarbeiter-Anmeldung, keine IP-/Ländersperre des Eingabebereichs) und kunden_wartung",
         "   (pausiert im Wartungsmodus der Angebotsseite), wartung_frei (bleibt bei Wartung der Oberfläche erreichbar:",
         "   Anmeldung, Abmelden, Status). Bei Konflikten nach einem Rebase einfach neu erzeugen. */",
         "if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar", "",
         "const AKTIONEN = ["]
    for name, a in sorted(aktionen_tabelle(rw).items()):
        felder = ", ".join(f"'{k}' => {php_wert(a[k])}" for k in ("modul", "oberflaeche", "schreibend", "oeffentlich", "kunden_wartung", "wartung_frei"))
        z.append(f"    '{name}' => [{felder}],")
    z.append("];")
    return "\n".join(z) + "\n"


MODULE_LISTE = "app/api/lib/module-liste.php"


def php_ausdruck(v, einzug: str = "") -> str:
    """Python-Wert als PHP-Ausdruck (Listen, Tabellen, Text, Zahl, Wahrheitswert, null) – stabil sortiert nach Eingabe."""
    if v is None:
        return "null"
    if isinstance(v, (bool, str)):
        return php_wert(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(php_ausdruck(x, einzug) for x in v) + "]"
    if isinstance(v, dict):
        return "[" + ", ".join(f"{php_wert(str(k))} => {php_ausdruck(x, einzug)}" for k, x in v.items()) + "]"
    raise TypeError(f"Nicht darstellbar: {v!r}")


def kachel_ziel(m: dict) -> str | None:
    ziel = m.get("kachel_ziel")
    if ziel:
        return ziel if "." in ziel else f"{m['id']}.{ziel}"
    intern = [o for o in m.get("oberflaeche", []) if o.get("art") == "intern"]
    return f"{m['id']}.{intern[0]['id']}" if intern else None


def module_php(rw: Regelwerk) -> str:
    """Laufzeitfassung des Modulregisters (ohne Code-Pfade, Agenten oder Hinweise) und der Entscheidungstabelle.
    Der Server wertet ausschließlich diese Tabelle aus (GR-102) – keine zweite, handgeschriebene Logik."""
    z = ["<?php", "declare(strict_types=1);",
         "/* ERZEUGT von `python3 werkzeuge/regeln.py erzeugen` aus regeln/module.toml und regeln/wartung.toml –",
         "   nicht von Hand ändern. Auswertung: lib/module.php. Bei Konflikten nach einem Rebase neu erzeugen. */",
         "if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar", "",
         "const MODULE = ["]
    for m in sorted(rw.modulliste, key=lambda m: (m.get("reihenfolge", 1000), m["id"])):
        obs = {}
        for o in m.get("oberflaeche", []):
            obs[o["id"]] = {"name": o["name"], "art": o["art"], "adresse": o["adresse"], "ziel": o.get("ziel"),
                            "entwicklung": o["entwicklung"], "freigabe": o["freigabe"], "sperrbar": o["sperrbar"],
                            "dns": o.get("dns", True)}
        eintrag = {"name": m["name"], "beschreibung": m.get("beschreibung", ""), "icon": m.get("icon", ""),
                   "reihenfolge": m.get("reihenfolge"), "dashboard": bool(m.get("dashboard")), "teil_von": m.get("teil_von"),
                   "kachel_ziel": kachel_ziel(m) if m.get("dashboard") else None,
                   "abhaengigkeiten": list(m.get("abhaengigkeiten", [])), "oberflaechen": obs}
        z.append(f"    {php_wert(m['id'])} => {php_ausdruck(eintrag)},")
    z.append("];")
    w = rw.wartung
    z.append("const MODUL_FREIGABE_ERLAUBT = " + php_ausdruck({k: list(v) for k, v in w.get("freigabe_erlaubt", {}).items()}) + ";")
    z.append("const MODUL_REGELN = [")
    for r in sorted(w.get("regel", []), key=lambda r: r.get("nr", 0)):
        z.append("    " + php_ausdruck({"nr": r["nr"], "wenn": dict(r.get("wenn", {})), "zugang": r["zugang"], "http": r["http"],
                                         "kachel": r["kachel"], "hinweis": bool(r.get("hinweis", False))}) + ",")
    z.append("];")
    return "\n".join(z) + "\n"


def pruefe_aktionen(rw: Regelwerk) -> None:
    ids = rw.modul_ids()
    oberflaechen = {f"{m['id']}.{o.get('id')}": o for m in rw.modulliste for o in m.get("oberflaeche", [])}
    gesehen = {}
    for datei, inhalt in sorted(rw.aktionen.items()):
        ort = f"regeln/aktionen/{datei}.toml"
        if inhalt.get("schema") != 1:
            rw.f(f"{ort}: schema = 1 fehlt")
        if inhalt.get("modul") != datei:
            rw.f(f"{ort}: modul muss „{datei}“ lauten (Dateiname = Modul)")
        if datei not in ids:
            rw.f(f"{ort}: Modul „{datei}“ gibt es nicht in regeln/module.toml")
        for name, a in sorted((inhalt.get("aktion") or {}).items()):
            wo = f"Aktion {name} ({ort})"
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                rw.f(f"{wo}: ungültiger Name")
            if name in gesehen:
                rw.f(f"{wo}: schon in {gesehen[name]} registriert – jede Aktion gehört genau einem Modul")
                continue
            gesehen[name] = ort
            unbekannt = set(a) - {"oberflaeche", "schreibend", "oeffentlich", "kunden_wartung", "wartung_frei"}
            if unbekannt:
                rw.f(f"{wo}: unbekannte Felder {', '.join(sorted(unbekannt))}")
            ob = oberflaechen.get(a.get("oberflaeche", ""))
            if not ob:
                rw.f(f"{wo}: oberflaeche „{a.get('oberflaeche', '')}“ gibt es nicht (Form <modul>.<oberfläche>)")
            if a.get("schreibend", False) not in (True, False, "post"):
                rw.f(f"{wo}: schreibend muss true, false oder \"post\" sein")
            for feld in ("oeffentlich", "kunden_wartung", "wartung_frei"):
                if not isinstance(a.get(feld, False), bool):
                    rw.f(f"{wo}: {feld} muss true oder false sein")
            if ob and a.get("oeffentlich") and ob.get("art") != "extern":
                rw.f(f"{wo}: öffentliche Aktion auf interner Oberfläche {a['oberflaeche']} (GR-104)")
            if ob and ob.get("art") == "extern" and not a.get("oeffentlich"):
                rw.f(f"{wo}: Mitarbeiter-Aktion auf externer Oberfläche {a['oberflaeche']} – auf die interne Oberfläche legen (GR-104, GR-109)")
            if a.get("kunden_wartung") and not a.get("oeffentlich"):
                rw.f(f"{wo}: kunden_wartung nur für öffentliche Kundenaktionen (GR-009)")
            if a.get("wartung_frei") and a.get("oeffentlich"):
                rw.f(f"{wo}: wartung_frei nur für Mitarbeiter-Aktionen (öffentliche regelt kunden_wartung)")
            if a.get("wartung_frei") and a.get("schreibend") is True and name not in WARTUNG_FREI_SCHREIBEND:
                rw.f(f"{wo}: schreibende Aktion als wartung_frei – nur Anmeldung und eigener Zugang erlaubt (GR-107)")
    code = aktionen_im_code(rw.wurzel)
    for name in sorted(code - set(gesehen)):
        rw.f(f"Aktion {name} wird im Code bearbeitet, ist aber in keinem regeln/aktionen/*.toml registriert (GR-109)")
    for name in sorted(set(gesehen) - code):
        rw.f(f"Aktion {name} ist registriert ({gesehen[name]}), wird im Code aber nicht bearbeitet")
    liste = rw.wurzel / AKTIONEN_LISTE
    if gesehen or liste.is_file():
        if not liste.is_file() or liste.read_text(encoding="utf-8") != aktionen_php(rw):
            rw.f(f"{AKTIONEN_LISTE} passt nicht zu regeln/aktionen/ – `python3 werkzeuge/regeln.py erzeugen` ausführen")
    mliste = rw.wurzel / MODULE_LISTE
    if mliste.is_file() or (rw.wurzel / "app/api/lib/module.php").is_file():
        if not mliste.is_file() or mliste.read_text(encoding="utf-8") != module_php(rw):
            rw.f(f"{MODULE_LISTE} passt nicht zu regeln/module.toml bzw. regeln/wartung.toml – `python3 werkzeuge/regeln.py erzeugen` ausführen")


def pruefen(rw: Regelwerk) -> Regelwerk:
    liste = dateien(rw.wurzel)
    pruefe_module(rw)
    pruefe_pfade(rw, liste)
    pruefe_daten(rw, liste)
    pruefe_rechte(rw)
    pruefe_tests(rw)
    pruefe_katalog(rw)
    pruefe_wartung(rw)
    pruefe_caddy(rw)
    pruefe_aktionen(rw)
    return rw


# ─────────────────────────────── Änderungsfolgen ───────────────────────────────

def geaenderte_dateien(wurzel: Path, basis: str) -> list:
    def git(*args):
        return subprocess.run(["git", *args], cwd=wurzel, capture_output=True, text=True, check=True).stdout.split("\n")
    liste = set(git("diff", "--name-only", f"{basis}...HEAD")) | set(git("diff", "--name-only", "HEAD"))
    liste |= set(git("ls-files", "--others", "--exclude-standard"))
    return sorted(p for p in liste if p)


def folgen(rw: Regelwerk, liste: list) -> dict:
    zugriffe = speicherzugriffe(rw.wurzel, [p for p in liste if (rw.wurzel / p).is_file()])
    dateien_info, module, koord, docs = [], set(), {}, {}
    for p in liste:
        mid, mu = eigentuemer(rw, p)
        k = koordination(rw, p)
        dateien_info.append({"datei": p, "modul": mid, "muster": mu, "koordination": k})
        if mid and not mid.startswith("!"):
            module.add(mid)
        for b in k:
            koord.setdefault(b, []).append(p)
        for doc in zugriffe.get(p, {}).get("schreibt", set()) | zugriffe.get(p, {}).get("liest", set()):
            e = dokument_eintrag(rw, doc)
            if e:
                docs[e["name"]] = e
    # Ändert sich ein Modul, sind Module betroffen, die davon abhängen (Plattformkern: nur ausgewiesen, nicht alle Tests)
    abhaengige = {m["id"] for m in rw.modulliste for a in m.get("abhaengigkeiten", []) if a in module} - module
    leser = {x for e in docs.values() for x in e.get("leser", []) + e.get("schreiber", []) + [e["eigentuemer"]]} - module
    # Relevante Regeln: das Modul ist betroffen und die Regel nennt es, oder die Änderung berührt Daten der Regel.
    # Wer den Katalog selbst ändert, bekommt alle Regeln angezeigt.
    alle_regeln = "regeln/katalog.toml" in liste
    regeln = [r for r in rw.katalog.get("regel", [])
              if alle_regeln or set(r.get("module", [])) & module or set(r.get("daten", [])) & set(docs)]
    gruppen = set()
    for mid in module:
        m = rw.modul(mid) or {}
        if mid != "plattform":
            gruppen |= set(m.get("testgruppen", []))
    weitere = []
    # Tests einer Regel nur, wenn das verantwortliche Modul oder ihre Daten berührt sind (sonst liefe für jede
    # Modul-Änderung die Testmenge aller plattformweiten Regeln mit).
    for r in regeln:
        if r.get("verantwortlich") not in module and not set(r.get("daten", [])) & set(docs):
            continue
        for t in r.get("tests", []):
            if t.startswith("e2e:"):
                gruppen.add(t[4:])
            elif t not in weitere:
                weitere.append(t)
    voll = bool(koord) or "plattform" in module
    return {
        "dateien": dateien_info,
        "module": sorted(module),
        "abhaengige_module": sorted(abhaengige),
        "dokumente": sorted(docs),
        "daten_mitbetroffen": sorted(leser),
        "koordination": koord,
        "regeln": [{"id": r["id"], "titel": r["titel"]} for r in regeln],
        "testgruppen": sorted(gruppen),
        "weitere_pruefungen": weitere,
        "volle_suite_noetig": voll,
        "hinweise": {mid: (rw.modul(mid) or {}).get("hinweise", []) for mid in sorted(module)},
    }


def folgen_text(e: dict) -> str:
    z = ["## Änderungsfolgen (werkzeuge/regeln.py betroffen)", ""]
    ohne = [d["datei"] for d in e["dateien"] if not d["modul"] or d["modul"].startswith("!")]
    z.append(f"**Module:** {', '.join(e['module']) or '–'}")
    if e["abhaengige_module"]:
        z.append(f"**Abhängige Module (Schnittstellen prüfen):** {', '.join(e['abhaengige_module'])}")
    if e["dokumente"]:
        z.append(f"**Berührte Daten:** {', '.join(e['dokumente'])}"
                 + (f" – mitbetroffen: {', '.join(e['daten_mitbetroffen'])}" if e["daten_mitbetroffen"] else ""))
    if e["koordination"]:
        z.append("**Koordinationspflichtig:**")
        z += [f"- {b}: {', '.join(p)}" for b, p in e["koordination"].items()]
    if e["regeln"]:
        z.append("**Regeln:** " + ", ".join(f"{r['id']} {r['titel']}" for r in e["regeln"]))
    if e["testgruppen"]:
        z.append(f"**Tests während der Entwicklung:** `python3 tests/run_e2e.py {' '.join(e['testgruppen'])}`")
    if e["weitere_pruefungen"]:
        z.append("**Weitere Prüfungen:** " + "; ".join(e["weitere_pruefungen"]))
    z.append("**Vor dem PR:** volle E2E-Suite in beiden Speicherarten (AGENTS.md, Definition of Done)"
             + (" – hier zwingend, da Plattformkern/koordinationspflichtige Bereiche berührt sind." if e["volle_suite_noetig"] else "."))
    for mid, hs in e["hinweise"].items():
        for h in hs:
            z.append(f"- Hinweis {mid}: {h}")
    if ohne:
        z.append("**Ohne Eigentümer (regeln/module.toml ergänzen):** " + ", ".join(ohne))
    return "\n".join(z)


def steckbrief(rw: Regelwerk, mid: str) -> str:
    m = rw.modul(mid)
    if not m:
        return f"Unbekanntes Modul „{mid}“. Bekannt: {', '.join(sorted(rw.modul_ids()))}"
    liste = dateien(rw.wurzel)
    eigene = [p for p in liste if eigentuemer(rw, p)[0] == mid]
    docs = [d for d in rw.daten.get("dokument", []) if d.get("eigentuemer") == mid]
    fremd = [d for d in rw.daten.get("dokument", []) if mid in d.get("leser", []) + d.get("schreiber", [])]
    rechte = [p for p, z in rw.rechte.get("zuordnung", {}).items() if z == mid]
    regeln = [r for r in rw.katalog.get("regel", []) if mid in r.get("module", [])]
    abh = [x["id"] for x in rw.modulliste if mid in x.get("abhaengigkeiten", [])]
    z = [f"# {m['name']} ({mid}) – Agent „{m.get('agent')}“", m.get("beschreibung", ""), ""]
    if m.get("teil_von"):
        z.append(f"Technisch Teil von: {m['teil_von']} (Kachel → {m.get('kachel_ziel')})")
    for o in m.get("oberflaeche", []):
        z.append(f"- Oberfläche {o['id']}: {o['adresse']} ({o['art']}, {o['entwicklung']}, Freigabe {o['freigabe']}"
                 + (f", künftig {o['ziel']}" if o.get("ziel") else "") + (", noch ohne DNS" if o.get("dns") is False else "") + ")")
    z += ["", f"Hängt ab von: {', '.join(m.get('abhaengigkeiten', [])) or '–'}; davon abhängig: {', '.join(abh) or '–'}",
          f"Eigene Dateien ({len(eigene)}): " + (", ".join(eigene[:40]) + (" …" if len(eigene) > 40 else "") if eigene else "–"),
          f"Geplante Orte für neuen Code: {', '.join(m.get('pfade_geplant', [])) or '–'}",
          f"Eigene Daten: {', '.join(d['name'] + ' [' + d['schutz'] + ']' for d in docs) or '–'}",
          f"Fremde Daten (lesen/schreiben): {', '.join(d['name'] + ' (' + d['eigentuemer'] + ')' for d in fremd) or '–'}",
          f"Rechte: {', '.join(rechte) or '–'} (neue Rechte: „{mid}.<recht>“)",
          "Regeln: " + (", ".join(f"{r['id']} {r['titel']}" for r in regeln) or "–"),
          f"Testgruppen: {' '.join(m.get('testgruppen', [])) or '– (neue Gruppen in tests/run_e2e.py anlegen)'}"]
    z += [f"- Hinweis: {h}" for h in m.get("hinweise", [])]
    return "\n".join(z)


# ─────────────────────────────── Aufruf ───────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wurzel", type=Path, default=WURZEL, help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="befehl", required=True)
    sub.add_parser("pruefen", help="Regelwerk und Modulgrenzen prüfen (CI)")
    b = sub.add_parser("betroffen", help="Änderungsfolgen für Dateien bzw. gegenüber einer Basis ermitteln")
    b.add_argument("dateien", nargs="*")
    b.add_argument("--basis", help="Git-Referenz, z. B. origin/main")
    b.add_argument("--json", action="store_true")
    sub.add_parser("erzeugen", help=f"{AKTIONEN_LISTE} und {MODULE_LISTE} aus regeln/ schreiben")
    s = sub.add_parser("modul", help="Steckbrief eines Moduls")
    s.add_argument("id")
    a = ap.parse_args(argv)
    wurzel = a.wurzel.resolve()
    rw = laden(wurzel)
    if a.befehl == "pruefen":
        pruefen(rw)
        for t in rw.warnungen:
            print(f"Warnung: {t}")
        for t in rw.fehler:
            print(f"::error::{t}" if __import__("os").environ.get("GITHUB_ACTIONS") else f"FEHLER: {t}")
        if rw.fehler:
            print(f"\n{len(rw.fehler)} Fehler im Regelwerk (regeln/*.toml, docs/plattform/multi-agent.md).")
            return 1
        n = len(rw.modulliste)
        print(f"OK: Regelwerk stimmig – {n} Module, {len(rw.daten.get('dokument', []))} Dokumente, "
              f"{len(rw.katalog.get('regel', []))} Regeln, {len(dateien(wurzel))} Dateien zugeordnet.")
        return 0
    if a.befehl == "erzeugen":
        (wurzel / AKTIONEN_LISTE).write_text(aktionen_php(rw), encoding="utf-8")
        (wurzel / MODULE_LISTE).write_text(module_php(rw), encoding="utf-8")
        print(f"geschrieben: {AKTIONEN_LISTE} ({len(aktionen_tabelle(rw))} Aktionen), {MODULE_LISTE} "
              f"({len(rw.modulliste)} Module) – danach: python3 werkzeuge/integritaet.py --setzen")
        return 0
    if a.befehl == "betroffen":
        liste = sorted(set(a.dateien) | (set(geaenderte_dateien(wurzel, a.basis)) if a.basis else set()))
        if not liste:
            print("Keine Dateien angegeben (Dateien nennen oder --basis origin/main).")
            return 2
        e = folgen(rw, liste)
        print(json.dumps(e, ensure_ascii=False, indent=2) if a.json else folgen_text(e))
        return 0
    print(steckbrief(rw, a.id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
