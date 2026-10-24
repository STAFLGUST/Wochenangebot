#!/usr/bin/env python3
"""Nachschlageteil der Entwickler-Dokumentation aus dem Code erzeugen und prüfen (nur Python-Standardbibliothek).

  python3 werkzeuge/doku.py erzeugen     docs/entwickler/referenz/*.md neu schreiben
  python3 werkzeuge/doku.py pruefen      CI: Ausgang 1, wenn die Dateien nicht zum Code passen oder eine Code-Datei
                                         keinen beschreibenden Kopfkommentar hat

Quellen (nie von Hand in der Referenz ändern, sondern dort):
  api.md      regeln/aktionen/*.toml + Rechteprüfungen in app/api/aktionen/*.php, orders.php, order_outbox.php
  rechte.md   PERMS in app/api/lib/rechte.php, Modulzugang aus regeln/module.toml, regeln/berechtigungen.toml
  daten.md    regeln/datenverantwortung.toml
  module.md   regeln/module.toml
  dateien.md  versionierte Dateien mit Modul (regeln/module.toml) und erster Zeile ihres Kopfkommentars

Die erklärenden Kapitel (docs/entwickler/0*.md) pflegt, wer den Code ändert (AGENTS.md, Definition of Done).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regeln as rg  # noqa: E402  (gleiches Verzeichnis)

WURZEL = rg.WURZEL
ZIEL = "docs/entwickler/referenz"
KOPF = ("<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. "
        "Quelle: {quelle}. Die CI prüft, dass diese Datei zum Code passt. -->\n\n")

# Code-Dateien, die einen beschreibenden Kopfkommentar tragen müssen
CODE_ENDUNGEN = {".php", ".js", ".css", ".py", ".sh", ".html", ".ftl"}
CODE_ORTE = ("app/", "dashboard/", "deploy/", "werkzeuge/", "tests/", ".github/scripts/")
OHNE_KOPF = ("app/assets/vendor/", "tests/fixtures/", "app/api/geo/")   # fremde Dateien und Testdaten


def md(text: str) -> str:
    """Text für Markdown-Tabellen: Senkrechtstriche maskieren, Zeilenumbrüche entfernen."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


# ─────────────────────────────── Kopfkommentare ───────────────────────────────

def kopfkommentar(pfad: Path) -> str:
    """Erste Aussage des Kopfkommentars einer Datei ('' = keiner)."""
    try:
        text = pfad.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""
    endung = pfad.suffix.lower()
    zeilen = text.splitlines()
    roh = ""
    if endung in (".py",):
        m = re.match(r'(?:#![^\n]*\n)?(?:#[^\n]*coding[^\n]*\n)?\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', text, re.S)
        if m:
            roh = m.group(1)
        else:
            roh = _hash_kommentar(zeilen)
    elif endung in (".sh", ".toml", ".yml", ".yaml", ".conf", ".ini") or pfad.name in ("Caddyfile", "Dockerfile"):
        roh = _hash_kommentar(zeilen)
    elif endung in (".php", ".js", ".css"):
        anfang = text.find("/*", 0, 1500)   # Kopfkommentar am Dateianfang (darf lang sein, z. B. API-Übersicht)
        ende = text.find("*/", anfang + 2) if anfang >= 0 else -1
        roh = text[anfang + 2:ende].lstrip("*") if ende > 0 else ""
        if not roh:   # Zeilenkommentare am Anfang (JavaScript)
            roh = " ".join(z.strip()[2:].strip() for z in zeilen[:8] if z.strip().startswith("//"))
    elif endung in (".html", ".ftl"):
        m = re.search(r"<!--(.*?)-->", text[:4000], re.S) or re.search(r"<#--(.*?)-->", text[:4000], re.S)
        if m:
            roh = m.group(1)
        else:
            t = re.search(r"<title>(.*?)</title>", text, re.S)
            roh = ("Seite „" + t.group(1).strip() + "“") if t else ""
    elif endung == ".md":
        for z in zeilen:
            if z.startswith("#"):
                return z.lstrip("#").strip()
    return _erste_aussage(roh)


def _hash_kommentar(zeilen: list) -> str:
    teile = []
    for z in zeilen[:30]:
        s = z.strip()
        if s.startswith("#!") or "shellcheck" in s or s.startswith("# -*-"):
            continue
        if s.startswith("#"):
            teile.append(s.lstrip("#").strip())
            continue
        if teile or s:
            if s and not teile:
                continue
            break
    return " ".join(teile)


def _erste_aussage(roh: str) -> str:
    s = re.sub(r"\s+", " ", re.sub(r"^\s*\*+", "", roh, flags=re.M)).strip(" =-*")
    s = re.sub(r"^=+\s*|\s*=+$", "", s).strip()
    if not s:
        return ""
    # erster Satz (Punkt + Leerzeichen + Großbuchstabe), höchstens 220 Zeichen
    m = re.search(r"^(.{20,220}?[.:])\s+(?=[A-ZÄÖÜ(„])", s)
    satz = m.group(1) if m else s
    if len(satz) > 220:
        satz = satz[:217].rsplit(" ", 1)[0] + " …"
    return satz.rstrip(":")


def braucht_kopf(pfad: str) -> bool:
    p = Path(pfad)
    return (p.suffix.lower() in CODE_ENDUNGEN and pfad.startswith(CODE_ORTE) and not pfad.startswith(OHNE_KOPF)
            and not p.name.startswith("__") and not pfad.endswith("-liste.php"))


# ─────────────────────────────── API ───────────────────────────────

CASE_RE = re.compile(r"case\s+'([a-z0-9_]+)'\s*:")
PRUEF_RE = [
    (re.compile(r"require_perm_confirmed\(\s*'([a-z0-9_.]+)'"), "Recht {} + Bestätigung"),
    (re.compile(r"require_perm\(\s*'([a-z0-9_.]+)'"), "Recht {}"),
    (re.compile(r"require_admin_confirmation\("), "Administrator + Bestätigung"),
    (re.compile(r"require_auth\([^)]*'admin'\)"), "Administrator"),
    (re.compile(r"current_customer\(|require_customer\("), "Kunde"),
    (re.compile(r"require_auth\("), "angemeldet"),
]


def pruefungen_im_code(wurzel: Path) -> dict:
    """Aktion → (Datei, [Prüfungen]) aus den case-Blöcken der Aktionsdateien."""
    out = {}
    dateien = sorted((wurzel / "app/api/aktionen").glob("*.php")) + [wurzel / "app/api/orders.php", wurzel / "app/api/order_outbox.php"]
    for d in dateien:
        if not d.is_file():
            continue
        text = d.read_text(encoding="utf-8")
        treffer = list(CASE_RE.finditer(text))
        for i, m in enumerate(treffer):
            ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(text)
            block = text[m.end():ende]
            gefunden = []
            for rx, form in PRUEF_RE:
                for t in rx.finditer(block):
                    eintrag = form.format(t.group(1)) if "{}" in form else form
                    if eintrag not in gefunden:
                        gefunden.append(eintrag)
                if form == "angemeldet" and len(gefunden) > 1 and "angemeldet" in gefunden:
                    gefunden.remove("angemeldet")
            # „angemeldet“ nur, wenn nichts Genaueres gefunden wurde
            if len(gefunden) > 1 and "angemeldet" in gefunden:
                gefunden.remove("angemeldet")
            out.setdefault(m.group(1), (str(d.relative_to(wurzel)), gefunden))
    # Aktionen ohne eigenen case-Block (z. B. Bestellungen in orders.php): Datei, in der der Name vorkommt
    weitere = dateien + sorted(p for p in (wurzel / "app/api/lib").glob("*.php") if not p.name.endswith("-liste.php"))
    texte = {d: d.read_text(encoding="utf-8") for d in weitere if d.is_file()}
    for name in rg.aktionen_tabelle(rg.laden(wurzel)):
        if name not in out:
            for d, text in texte.items():
                if f"'{name}'" in text:
                    out[name] = (str(d.relative_to(wurzel)), ["siehe Datei"])
                    break
    return out


def api_md(rw) -> str:
    tab = rg.aktionen_tabelle(rw)
    code = pruefungen_im_code(rw.wurzel)
    z = ["# Referenz: API-Aktionen", "",
         KOPF.format(quelle="regeln/aktionen/*.toml, Rechteprüfungen in app/api/aktionen/*.php").strip(), "",
         "Aufruf: `/api/?action=<aktion>` (GET lesend, POST mit JSON und `X-CSRF-Token` schreibend). Ablauf im Server: "
         "[03-server.md](../03-server.md), Rechte: [04-anmeldung-rechte.md](../04-anmeldung-rechte.md). „Prüfung im Code“ "
         "ist aus den Aufrufen `require_perm`/`require_auth`/`require_admin_confirmation`/`current_customer` im "
         "`case`-Block gelesen – eine Hilfe zum Finden, maßgeblich ist der Code (Prüfungen in aufgerufenen Funktionen "
         "erscheinen hier nicht).", "",
         "Spalten: **Art** – lesend, schreibend (nur POST) oder post (GET liest, POST schreibt); **Kennzeichen** – "
         "öffentlich (ohne Mitarbeiteranmeldung), Kunden-Wartung, wartungsfrei, fremde Herkunft, eigene Anmeldung "
         "(siehe [regeln/aktionen/LIESMICH.md](../../../regeln/aktionen/LIESMICH.md)).", ""]
    nach_modul: dict = {}
    for name, a in sorted(tab.items()):
        nach_modul.setdefault(a["modul"], []).append((name, a))
    module = {m["id"]: m for m in rw.modulliste}
    z.append(f"{len(tab)} Aktionen in {len(nach_modul)} Modulen.")
    z.append("")
    for mid in sorted(nach_modul, key=lambda x: (module.get(x, {}).get("reihenfolge", 999), x)):
        z.append(f"## {module.get(mid, {}).get('name', mid)} (`{mid}`)")
        z.append("")
        z.append("| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |")
        z.append("| --- | --- | --- | --- | --- | --- |")
        for name, a in nach_modul[mid]:
            art = {True: "schreibend", False: "lesend", "post": "post"}[a["schreibend"]]
            kz = [k for k, t in (("oeffentlich", "öffentlich"), ("kunden_wartung", "Kunden-Wartung"), ("wartung_frei", "wartungsfrei"),
                                 ("fremde_herkunft", "fremde Herkunft"), ("lokale_anmeldung", "eigene Anmeldung")) if a.get(k)]
            kz_txt = ", ".join(t for k, t in (("oeffentlich", "öffentlich"), ("kunden_wartung", "Kunden-Wartung"), ("wartung_frei", "wartungsfrei"),
                                              ("fremde_herkunft", "fremde Herkunft"), ("lokale_anmeldung", "eigene Anmeldung")) if k in kz)
            datei, pr = code.get(name, ("", []))
            z.append(f"| `{name}` | `{a['oberflaeche']}` | {art} | {kz_txt or '–'} | {md(', '.join(pr)) or '–'} | "
                     + (f"`{datei}`" if datei else "–") + " |")
        z.append("")
    return "\n".join(z).rstrip() + "\n"


# ─────────────────────────────── Rechte ───────────────────────────────

PERM_ZEILE = re.compile(r"^\s*'([a-z][a-z0-9_.]*)'\s*=>\s*\[(.*)\],?\s*$", re.M)


def perms_aus_code(wurzel: Path) -> list:
    text = (wurzel / "app/api/lib/rechte.php").read_text(encoding="utf-8")
    block = re.search(r"const PERMS = \[(.*?)\n\];", text, re.S).group(1)
    out = []
    for m in PERM_ZEILE.finditer(block):
        inhalt = m.group(2)
        feld = lambda k: (re.search(r"'" + k + r"'\s*=>\s*'((?:[^'\\]|\\.)*)'", inhalt) or [None, ""])[1]
        liste = lambda k: re.findall(r"'([a-z0-9_.]+)'", (re.search(r"'" + k + r"'\s*=>\s*\[([^\]]*)\]", inhalt) or [None, ""])[1])
        out.append({"key": m.group(1), "g": feld("g"), "l": feld("l").replace("\\'", "'"), "k": feld("k"), "d": liste("d"), "r": liste("r")})
    return out


def rechte_md(rw) -> str:
    zu = rw.rechte.get("zuordnung", {})
    module = {m["id"]: m for m in rw.modulliste}
    rolle = {"viewer": "Nur ansehen", "editor": "Bearbeiter"}
    z = ["# Referenz: Rechte", "", KOPF.format(quelle="PERMS in app/api/lib/rechte.php, regeln/module.toml, regeln/berechtigungen.toml").strip(), "",
         "Administratoren haben alle Rechte. Standard = Rechte der Standardrollen ohne gespeicherte Änderung; eigene Rollen "
         "starten leer. Erklärung: [04-anmeldung-rechte.md](../04-anmeldung-rechte.md).", "",
         "## Modulzugang", "",
         "Für jedes Modul mit Kachel entsteht `<modul>.zugang` (lib/rechte.php, `perms_katalog`): Kachel im Dashboard und "
         "Oberfläche des Moduls; Standard: beide Standardrollen.", "",
         "| Recht | Modul |", "| --- | --- |"]
    for m in sorted(rw.modulliste, key=lambda m: (m.get("reihenfolge", 999), m["id"])):
        if m.get("dashboard") and rg.kachel_ziel(m):
            z.append(f"| `{m['id']}.zugang` | {md(m['name'])} |")
    z += ["", "## Rechte innerhalb der Module", "", "| Recht | Modul | Bereich | Art | Bezeichnung | Standard | setzt voraus |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for p in perms_aus_code(rw.wurzel):
        mid = zu.get(p["key"], p["key"].split(".")[0])
        art = {"sehen": "sehen", "machen": "bearbeiten"}.get(p["k"], p["k"])
        std = ", ".join(rolle.get(r, r) for r in p["d"]) or "–"
        z.append(f"| `{p['key']}` | {md(module.get(mid, {}).get('name', mid))} | {md(p['g'])} | {art} | {md(p['l'])} | {std} | "
                 + (", ".join(f"`{r}`" for r in p["r"]) or "–") + " |")
    na = rw.rechte.get("nur_administratoren", {})
    if na:
        z += ["", "## Nur Administratoren", ""] + [f"- {md(b)}" for b in na.get("bereiche", [])]
    return "\n".join(z).rstrip() + "\n"


# ─────────────────────────────── Daten, Module, Dateien ───────────────────────────────

def daten_md(rw) -> str:
    module = {m["id"]: m for m in rw.modulliste}
    z = ["# Referenz: Speicher-Dokumente", "", KOPF.format(quelle="regeln/datenverantwortung.toml").strip(), "",
         "Gelesen und geschrieben über `app/api/storage.php` (`store_read`, `store_write`, `with_lock`). Eigentümer und "
         "erlaubte Querzugriffe prüft `werkzeuge/regeln.py` (GR-101). Aufbau der wichtigsten Dokumente: "
         "[05-daten.md](../05-daten.md).", "",
         "| Dokument | Eigentümer | Schutz | Leser | Schreiber | Beschreibung |", "| --- | --- | --- | --- | --- | --- |"]
    for d in sorted(rw.daten.get("dokument", []), key=lambda d: (d.get("eigentuemer", ""), d["name"])):
        name = d["name"] + ("*" if d.get("dynamisch") else "")
        z.append(f"| `{md(name)}` | {md(module.get(d.get('eigentuemer'), {}).get('name', d.get('eigentuemer', '')))} | {d.get('schutz', '')} | "
                 f"{md(', '.join(d.get('leser', [])) or '–')} | {md(', '.join(d.get('schreiber', [])) or '–')} | "
                 f"{md(d.get('beschreibung', ''))}" + (f" – Historie: {md(d['historie'])}" if d.get("historie") else "") + " |")
    z += ["", "`*` Name wird im Code berechnet (z. B. je Monat oder je Angebot)."]
    return "\n".join(z).rstrip() + "\n"


def module_md(rw) -> str:
    z = ["# Referenz: Module und Oberflächen", "", KOPF.format(quelle="regeln/module.toml").strip(), "",
         "Steckbrief eines Moduls mit Pfaden, Daten, Rechten und Regeln: `python3 werkzeuge/regeln.py modul <id>`. "
         "Wer was nutzen darf (Entwicklung/Freigabe/Wartung): `regeln/wartung.toml`.", ""]
    for m in sorted(rw.modulliste, key=lambda m: (m.get("reihenfolge", 999), m["id"])):
        z.append(f"## {md(m['name'])} (`{m['id']}`)")
        z.append("")
        z.append(md(m.get("beschreibung", "")))
        z.append("")
        info = [f"Agent: `{m.get('agent', '–')}`"]
        if m.get("teil_von"):
            info.append(f"Teil von `{m['teil_von']}`")
        if m.get("abhaengigkeiten"):
            info.append("hängt ab von " + ", ".join(f"`{a}`" for a in m["abhaengigkeiten"]))
        if m.get("testgruppen"):
            info.append("Testgruppen: " + ", ".join(f"`{t}`" for t in m["testgruppen"]))
        z.append(" · ".join(info))
        z.append("")
        obs = m.get("oberflaeche", [])
        if obs:
            z += ["| Oberfläche | Art | Adresse | Entwicklung | Freigabe |", "| --- | --- | --- | --- | --- |"]
            for o in obs:
                z.append(f"| `{m['id']}.{o['id']}` {md(o['name'])} | {o['art']} | {md(o['adresse'])} | {o['entwicklung']} | {o['freigabe']} |")
            z.append("")
    return "\n".join(z).rstrip() + "\n"


def dateien_md(rw, liste: list) -> str:
    z = ["# Referenz: Dateien", "", KOPF.format(quelle="versionierte Dateien, regeln/module.toml, Kopfkommentare").strip(), "",
         "Jede Code-Datei beginnt mit einem Kopfkommentar; dessen erste Aussage steht hier. Ausführlicher: "
         "[../architektur.md](../../architektur.md) und die Kapitel dieser Dokumentation.", ""]
    gruppen: dict = {}
    for p in liste:
        if not p.startswith(("app/", "dashboard/", "deploy/", "werkzeuge/", "regeln/", ".github/", "tests/", "docs/")) and "/" in p:
            continue
        if p.startswith(("tests/fixtures/", "app/assets/vendor/", "app/assets/fonts/", "app/assets/icons/", "app/api/geo/")):
            continue
        if Path(p).suffix.lower() in (".png", ".jpg", ".jpeg", ".ico", ".woff2", ".woff", ".ttf", ".gz", ".xlsx", ".xls", ".pdf", ".json", ".txt", ".csv", ".svg", ".webp"):
            continue
        ordner = p.rsplit("/", 1)[0] if "/" in p else "(Wurzel)"
        gruppen.setdefault(ordner, []).append(p)
    for ordner in sorted(gruppen):
        z += [f"## `{ordner}/`" if ordner != "(Wurzel)" else "## Wurzel", "", "| Datei | Modul | Inhalt |", "| --- | --- | --- |"]
        for p in gruppen[ordner]:
            mid, _ = rg.eigentuemer(rw, p)
            z.append(f"| `{p.rsplit('/', 1)[-1]}` | {mid or '–'} | {md(kopfkommentar(rw.wurzel / p)) or '–'} |")
        z.append("")
    return "\n".join(z).rstrip() + "\n"


def alle(rw) -> dict:
    liste = rg.dateien(rw.wurzel)
    return {f"{ZIEL}/api.md": api_md(rw), f"{ZIEL}/rechte.md": rechte_md(rw), f"{ZIEL}/daten.md": daten_md(rw),
            f"{ZIEL}/module.md": module_md(rw), f"{ZIEL}/dateien.md": dateien_md(rw, liste)}


def main(argv=None) -> int:
    befehl = (argv or sys.argv[1:] or ["pruefen"])[0]
    rw = rg.laden()
    soll = alle(rw)
    if befehl == "erzeugen":
        for pfad, inhalt in soll.items():
            ziel = WURZEL / pfad
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_text(inhalt, encoding="utf-8")
        print("geschrieben: " + ", ".join(soll))
        return 0
    if befehl != "pruefen":
        print(__doc__)
        return 2
    fehler = []
    for pfad, inhalt in soll.items():
        ist = (WURZEL / pfad).read_text(encoding="utf-8") if (WURZEL / pfad).is_file() else None
        if ist != inhalt:
            fehler.append(f"{pfad} passt nicht zum Code – `python3 werkzeuge/doku.py erzeugen` ausführen und mit committen")
    for p in rg.dateien(WURZEL):
        if braucht_kopf(p) and not kopfkommentar(WURZEL / p):
            fehler.append(f"{p}: kein beschreibender Kopfkommentar (erste Zeilen: was die Datei tut) – Grundlage der Dateikarte")
    for f in fehler:
        print("FEHLER: " + f)
    if fehler:
        print(f"\n{len(fehler)} Fehler in der Entwickler-Dokumentation (docs/entwickler/, werkzeuge/doku.py).")
        return 1
    print(f"OK: Entwickler-Doku passt zum Code ({len(soll)} Referenzdateien).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
