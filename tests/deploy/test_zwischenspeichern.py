#!/usr/bin/env python3
"""Browser-Zwischenspeicher (Caddyfile, Abschnitt „zwischenspeichern“) mit echtem Caddy in der Fassung des Betriebs.

Der Abschnitt wird unverändert aus dem Caddyfile übernommen und vor einer Nachbildung der Anwendung geprüft (geschützte
Seiten leiten zur Anmeldung um, Schnittstelle mit eigener Angabe, Kartendatei mit eigener Angabe, sonst Dateien):
- Skripte und Stylesheets mit ?v= ein Jahr („immutable“), auf den Mitarbeiter-Hosts nur im Browser („private“)
- Schriften, Symbole und Logos ohne ?v= einen Tag, Bibliotheken unter assets/vendor/ und Seiten weiter „no-cache“
- nie gespeichert: Weiterleitung zur Anmeldung, 401, 404 – auch wenn die Adresse ?v= trägt
- eigene Angaben der Anwendung (Kartendatei, Schnittstelle) bleiben unberührt; Nachfrage (304) behält die Regel
Dazu statisch: welcher Block welchen Zwischenspeicher bekommt (öffentliche Seite „public“, alle anderen „private“,
Platzhalter-Hosts gar keinen). Braucht Docker (wie die Prüfung des Caddyfile in der CI)."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parent.parent.parent
caddy = (REPO / "Caddyfile").read_text(encoding="utf-8")
IMAGE = re.search(r"^\s*image:\s*(caddy:\S+)", (REPO / "docker-compose.yml").read_text(encoding="utf-8"), re.MULTILINE).group(1)
res = []


def check(name, ok, info=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  {info}" if info and not ok else ""), flush=True)


def bloecke():
    """Kopfzeile → Inhalt aller Blöcke der obersten Ebene (Sites und Abschnitte)."""
    return {m.group(1).strip(): m.group(2) for m in re.finditer(r"^([^\s#][^\n]*?) \{\n(.*?)^\}", caddy, re.MULTILINE | re.DOTALL)}


# ---------- statisch: Abschnitt und Zuordnung ----------
alle = bloecke()
abschnitt = re.search(r"^\(zwischenspeichern\) \{\n.*?^\}\n", caddy, re.MULTILINE | re.DOTALL)
check("Caddyfile: Abschnitt (zwischenspeichern) genau einmal", abschnitt and caddy.count("(zwischenspeichern)") == 1)
abschnitt = abschnitt.group(0) if abschnitt else ""
check("Abschnitt: nur erfolgreiche Antworten (2xx, 304) – nie Weiterleitungen oder Fehler",
      abschnitt.count("match status 2xx 304") == 2 and abschnitt.count("Cache-Control") == 2)
check("Abschnitt: Schnittstelle nie als Skript zwischengespeichert", "not path /api/*" in abschnitt)
check("„immutable“ und lange Speicherzeiten nur im Abschnitt",
      caddy.replace(abschnitt, "").count("immutable") == 0 and not re.search(r"max-age=(?!31536000\b)\d+", caddy.replace(abschnitt, "")))


def import_von(kopf):
    return re.findall(r"^\timport zwischenspeichern (\S+)$", alle.get(kopf, ""), re.MULTILINE)


mitarbeiter = next((k for k in alle if k.startswith("dashboard-stafl.de,")), "")
soll = {"{$DOMAIN}, www.{$DOMAIN}": ["public"], "test.{$DOMAIN}": ["private"], mitarbeiter: ["private"]}
for kopf, art in soll.items():
    check(f"{kopf[:40]}: zwischenspeichern {art[0]}, sonst „no-cache“", import_von(kopf) == art and '?Cache-Control "no-cache"' in alle.get(kopf, ""),
          import_von(kopf))
andere = [k for k in alle if not k.startswith("(") and k not in soll and "import zwischenspeichern" in alle[k]]
check("Platzhalter, Anmeldung und Weiterleitungen ohne Zwischenspeicher-Regeln", not andere, andere)

# ---------- Verhalten mit echtem Caddy ----------
if not shutil.which("docker"):
    check("Docker vorhanden (nötig für die Probe mit echtem Caddy)", False)
    sys.exit(1)

arbeit = Path(tempfile.mkdtemp(prefix="wa-zwischenspeichern-"))
www = arbeit / "www"
for rel in ("assets/app.css", "assets/fonts/f.woff2", "assets/icons/i.png", "assets/logo.png", "assets/vendor/maplibre/x.js",
            "module/qs/qs.js", "dashboard/dashboard.js", "index.html"):
    (www / rel).parent.mkdir(parents=True, exist_ok=True)
    (www / rel).write_text("/* Testinhalt */\n" * 200, encoding="utf-8")   # groß genug für die Kompression
konfig = "{\n\tauto_https off\n\tadmin off\n}\n\n" + abschnitt + """
# Nachbildung der Anwendung: geschützte Seiten → Anmeldung, Schnittstelle und Kartendatei mit eigenen Angaben
:8081 {
	handle /module/geschuetzt/* {
		redir https://login.example/anmelden 302
	}
	handle /api/geschlossen/* {
		header Cache-Control "no-store"
		respond "{}" 401
	}
	handle /api/* {
		header Cache-Control "no-store"
		respond "{}" 200
	}
	handle /karte/* {
		header Cache-Control "private, max-age=3600, no-transform"
		respond "x" 200
	}
	handle {
		root * /srv
		file_server
	}
}
"""
for port, art in ((8080, "private"), (8090, "public")):
    konfig += f"""
:{port} {{
	encode zstd gzip
	header {{
		?Cache-Control "no-cache"
		-Server
	}}
	import zwischenspeichern {art}
	reverse_proxy 127.0.0.1:8081
}}
"""
(arbeit / "Caddyfile").write_text(konfig, encoding="utf-8")
name = f"wa-zwischenspeichern-{int(time.time())}"
start = subprocess.run(["docker", "run", "-d", "--name", name, "-p", "127.0.0.1::8080", "-p", "127.0.0.1::8090",
                        "-v", f"{arbeit / 'Caddyfile'}:/etc/caddy/Caddyfile:ro", "-v", f"{www}:/srv:ro", IMAGE],
                       capture_output=True, text=True)
if start.returncode != 0:
    check("Caddy startet", False, start.stderr[-300:])
    sys.exit(1)
class OhneWeiterleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OHNE_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}), OhneWeiterleitung())   # Testhost nie über einen Proxy


def hostport(p):
    aus = subprocess.run(["docker", "port", name, str(p)], capture_output=True, text=True).stdout.split()
    return aus[0] if aus else ""


def abruf(basis, pfad, kopf=None):
    req = urllib.request.Request(basis + pfad, headers={"Accept-Encoding": "gzip", **(kopf or {})})
    try:
        r = OHNE_PROXY.open(req, timeout=10)
    except urllib.error.HTTPError as e:
        r = e
    r.read()
    return r.code, r.headers.get("Cache-Control") or "", r.headers.get("ETag") or ""


try:
    PRIV, OEFF = f"http://{hostport(8080)}", f"http://{hostport(8090)}"
    for _ in range(100):   # bereit, sobald die Nachbildung antwortet (kein fester Wartewert)
        try:
            if abruf(PRIV, "/index.html")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(0.1)
    JAHR, TAG = "private, max-age=31536000, immutable", "private, max-age=86400"
    faelle = [
        ("/assets/app.css?v=abc", 200, JAHR, "Stylesheet mit ?v= ein Jahr, nur im Browser"),
        ("/module/qs/qs.js?v=1a2b", 200, JAHR, "Skript einer Modulseite mit ?v= ein Jahr"),
        ("/dashboard/dashboard.js?v=1a2b", 200, JAHR, "Skript des Dashboards mit ?v= ein Jahr"),
        ("/assets/app.css", 200, "no-cache", "ohne ?v= weiter mit Rückfrage"),
        ("/assets/vendor/maplibre/x.js", 200, "no-cache", "Bibliothek ohne ?v= (lädt detailkarte.js) mit Rückfrage"),
        ("/assets/fonts/f.woff2", 200, TAG, "Schrift einen Tag"),
        ("/assets/icons/i.png", 200, TAG, "Symbol einen Tag"),
        ("/assets/logo.png", 200, TAG, "Logo einen Tag"),
        ("/index.html", 200, "no-cache", "Seite mit Rückfrage"),
        ("/module/geschuetzt/x.js?v=1a2b", 302, "no-cache", "Weiterleitung zur Anmeldung nie gespeichert (auch mit ?v=)"),
        ("/assets/fehlt.css?v=1a2b", 404, "no-cache", "fehlende Datei nie gespeichert"),
        ("/api/geschlossen/x.js?v=1", 401, "no-store", "Schnittstelle ohne Anmeldung (401) behält „no-store“"),
        ("/api/x.js?v=1", 200, "no-store", "Schnittstelle behält „no-store“ (nie als Skript gespeichert)"),
        ("/karte/k.pmtiles", 200, "private, max-age=3600, no-transform", "Kartendatei behält die Angabe der Anwendung"),
    ]
    for pfad, code, cc, text in faelle:
        ist = abruf(PRIV, pfad)
        check(f"Mitarbeiter-Host {pfad}: {text}", ist[:2] == (code, cc), ist[:2])
    _, _, etag = abruf(PRIV, "/assets/fonts/f.woff2")
    ist = abruf(PRIV, "/assets/fonts/f.woff2", {"If-None-Match": etag})
    check("Nachfrage nach einem Tag (304) behält die Speicherzeit", ist[:2] == (304, TAG), ist[:2])
    for pfad, code, cc, text in (("/assets/app.css?v=abc", 200, "public, max-age=31536000, immutable", "Stylesheet mit ?v= ein Jahr"),
                                 ("/assets/fonts/f.woff2", 200, "public, max-age=86400", "Schrift einen Tag"),
                                 ("/module/geschuetzt/x.js?v=1a2b", 302, "no-cache", "Weiterleitung nie gespeichert"),
                                 ("/assets/app.css", 200, "no-cache", "ohne ?v= mit Rückfrage")):
        ist = abruf(OEFF, pfad)
        check(f"Öffentliche Seite {pfad}: {text}", ist[:2] == (code, cc), ist[:2])
finally:
    if not all(res):
        print(subprocess.run(["docker", "logs", "--tail", "20", name], capture_output=True, text=True).stderr[-1500:])
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    shutil.rmtree(arbeit, ignore_errors=True)

print(f"\n{sum(res)}/{len(res)} bestanden")
sys.exit(0 if all(res) else 1)
