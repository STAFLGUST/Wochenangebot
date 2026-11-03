#!/usr/bin/env python3
"""bunny.net vor dem Server (Caddyfile, Abschnitt „cdn“) mit echtem Caddy in der Fassung des Betriebs.

Statisch: jeder Site-Block bindet den Abschnitt ein, jede Weiterleitung an Anwendung oder Keycloak gibt die Besucher-IP
weiter und den Schlüssel nie; Compose und .env-Vorlage lassen das CDN standardmäßig aus.
Verhalten (Abschnitt unverändert aus dem Caddyfile, davor eine Nachbildung der Anwendung, die die erhaltenen Köpfe
zurückgibt):
- ohne Schlüssel: alles wie bisher – Besucher-IP ist die Adresse der Verbindung, kein Kopf eines Besuchers ändert das
- mit Schlüssel: nur mit dem richtigen Kopf „X-Stafl-Cdn“ gilt X-Real-IP von bunny – und nur, wenn sie genau eine
  IP-Adresse ist (IPv4 oder IPv6; Liste, Text oder leer = Adresse der Verbindung); falscher Schlüssel = wie ohne CDN;
  die Anwendung bekommt den Schlüssel nie; Antwortkopf „Stafl-Cdn: erkannt“ nur über bunny
- zu kurzer Schlüssel: nie vertraut, Sperre bleibt aus
- CDN_PFLICHT=1: ohne richtigen Kopf 403 (auch vor anderen handle-Blöcken wie bei der Anmeldung), mit Kopf durch;
  auch Abrufe vom Server selbst (über die Docker-Weiterleitung mit privater Adresse – so erscheinen auch Besucher über
  IPv6) nur mit Schlüssel; die Prüfung nach dem Einspielen (deploy/freigabe-einspielen.sh) schickt ihn mit
Die Probe „öffentlicher“ Besucher läuft in einem Docker-Netz mit Dokumentationsadressen (198.51.100.0/24, kein privates
Netz). Braucht Docker (wie die Prüfung des Caddyfile in der CI)."""
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
compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
vorlage = (REPO / ".env.example").read_text(encoding="utf-8")
IMAGE = re.search(r"^\s*image:\s*(caddy:\S+)", compose, re.MULTILINE).group(1)
res = []


def check(name, ok, info=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  {info}" if info and not ok else ""), flush=True)


# ---------- statisch ----------
abschnitt = re.search(r"^\(cdn\) \{\n.*?^\}\n", caddy, re.MULTILINE | re.DOTALL)
check("Caddyfile: Abschnitt (cdn) genau einmal", abschnitt and caddy.count("(cdn) {") == 1)
abschnitt = abschnitt.group(0) if abschnitt else ""
check("Abschnitt: Schlüssel nur gültig mit 32–128 Buchstaben/Ziffern (leer oder kurz = nie vertraut, Sperre aus)",
      abschnitt.count('"{$CDN_SCHLUESSEL}".matches("^[A-Za-z0-9]{32,128}$")') == 2)
check("Abschnitt: Sperre nur mit CDN_PFLICHT=1, Ausnahme nur für den Caddy-Container selbst (keine privaten Netze)",
      '"{$CDN_PFLICHT}" == "1"' in abschnitt and "not remote_ip 127.0.0.1/8 ::1" in abschnitt and "private_ranges" not in abschnitt)
check("Abschnitt: Besucher-IP von bunny nur als einzelne IP-Adresse", "{header.X-Real-IP}.matches(" in abschnitt.split("vars @cdn")[0])
einspielen = (REPO / "deploy" / "freigabe-einspielen.sh").read_text(encoding="utf-8")
pruefabruf = next((z for z in einspielen.splitlines() if z.startswith("pruefabruf()")), "")
check("Prüfung nach dem Einspielen: alle Abrufe mit dem Schlüssel aus .env, nicht in der Prozessliste (curl -K -)",
      "CDN_KEY=$(envwert CDN_SCHLUESSEL)" in einspielen and "curl -K -" in pruefabruf
      and not re.search(r'curl -f?sS -m 5 --resolve "\$HEALTH_HOST"', einspielen) and einspielen.count('pruefabruf -') >= 4)
sites = {m.group(1): m.group(2) for m in re.finditer(r"^([^\s#(][^\n]*?) \{\n(.*?)^\}", caddy, re.MULTILINE | re.DOTALL)}
check("jeder Site-Block bindet den Abschnitt zuerst ein", sites and all(inhalt.startswith("\timport cdn\n") for inhalt in sites.values()),
      [k for k, v in sites.items() if not v.startswith("\timport cdn\n")])
ziele = re.findall(r"^(\t+)(reverse_proxy|forward_auth)[^\n]*\{\n(.*?)^\1\}", caddy, re.MULTILINE | re.DOTALL)
ohne = [z[1] for z in ziele if "header_up X-Forwarded-For {besucher_ip}" not in z[2] or "header_up -X-Stafl-Cdn" not in z[2]]
check("jede Weiterleitung (Anwendung, Testumgebung, Keycloak, Prüfung vor der Anmeldung) mit Besucher-IP und ohne Schlüssel",
      len(ziele) == caddy.count("reverse_proxy ") + caddy.count("forward_auth ") == 5 and not ohne, (len(ziele), ohne))
check("Compose: Caddy bekommt CDN_SCHLUESSEL (leer) und CDN_PFLICHT (0)",
      "CDN_SCHLUESSEL: ${CDN_SCHLUESSEL:-}" in compose and "CDN_PFLICHT: ${CDN_PFLICHT:-0}" in compose)
check(".env-Vorlage: CDN aus, ohne Schlüssel", re.search(r"^CDN_SCHLUESSEL=$", vorlage, re.MULTILINE) and re.search(r"^CDN_PFLICHT=0$", vorlage, re.MULTILINE))

# ---------- Verhalten mit echtem Caddy ----------
if not shutil.which("docker"):
    check("Docker vorhanden (nötig für die Probe mit echtem Caddy)", False)
    sys.exit(1)

SCHLUESSEL = "0123456789abcdef" * 4   # nur für diesen Test
ECHT, FALSCH = "203.0.113.7", "192.0.2.66"
WEITER = "\t\theader_up X-Forwarded-For {besucher_ip}\n\t\theader_up -X-Stafl-Cdn\n"
konfig = "{\n\tauto_https off\n\tadmin off\n}\n\n" + abschnitt + f"""
# Nachbildung der Anwendung: gibt die erhaltenen Köpfe zurück
:8081 {{
	respond "xff=[{{header.X-Forwarded-For}}] cdn=[{{header.X-Stafl-Cdn}}]" 200
}}

:8080 {{
	import cdn
	# wie bei der Anmeldung: eigener handle-Block vor der Weiterleitung
	@anmeldung path /anmeldung/*
	handle @anmeldung {{
		reverse_proxy 127.0.0.1:8081 {{
	{WEITER}	}}
	}}
	reverse_proxy 127.0.0.1:8081 {{
{WEITER}	}}
}}
"""
arbeit = Path(tempfile.mkdtemp(prefix="wa-cdn-"))
(arbeit / "Caddyfile").write_text(konfig, encoding="utf-8")
stempel = int(time.time())
netz = f"wa-cdn-{stempel}"
namen = []


def docker(*args, pruefen=True):
    r = subprocess.run(["docker", *args], capture_output=True, text=True)
    if pruefen and r.returncode != 0:
        raise RuntimeError(" ".join(args[:3]) + ": " + r.stderr[-300:])
    return r


def caddy_start(kennung, umgebung, netzwerk=None, port=False):
    name = f"wa-cdn-{kennung}-{stempel}"
    args = ["run", "-d", "--name", name, "-v", f"{arbeit / 'Caddyfile'}:/etc/caddy/Caddyfile:ro"]
    if netzwerk:
        args += ["--network", netzwerk]
    if port:
        args += ["-p", "127.0.0.1::8080"]
    for k, v in umgebung.items():
        args += ["-e", f"{k}={v}"]
    docker(*args, IMAGE)
    namen.append(name)
    return name


def ip(name):
    return docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name).stdout.strip()


def abruf(ziel, pfad="/", kopf=None):
    """Abruf aus dem Besucher-Container (öffentliche Adresse): (Status, Antwortköpfe, Inhalt)."""
    args = ["exec", besucher, "wget", "-q", "-S", "-T", "5", "-O", "-"]
    for k, v in (kopf or {}).items():
        args += ["--header", f"{k}: {v}"]
    r = docker(*args, f"http://{ip(ziel)}:8080{pfad}", pruefen=False)
    status = re.findall(r"HTTP/1\.\d (\d{3})", r.stderr)
    return (int(status[-1]) if status else 0), r.stderr, r.stdout


try:
    docker("network", "create", "--subnet", "198.51.100.0/24", netz)
    ohne = caddy_start("ohne", {"CDN_PFLICHT": "1"}, netz)                                    # kein Schlüssel: wie bisher
    mit = caddy_start("mit", {"CDN_SCHLUESSEL": SCHLUESSEL, "CDN_PFLICHT": "0"}, netz)          # Schlüssel, ohne Sperre
    pflicht = caddy_start("pflicht", {"CDN_SCHLUESSEL": SCHLUESSEL, "CDN_PFLICHT": "1"}, netz)  # Schlüssel und Sperre
    kurz = caddy_start("kurz", {"CDN_SCHLUESSEL": "kurz1234", "CDN_PFLICHT": "1"}, netz)        # ungültiger Schlüssel
    server = caddy_start("server", {"CDN_SCHLUESSEL": SCHLUESSEL, "CDN_PFLICHT": "1"}, port=True)  # Abruf vom Server selbst
    besucher = f"wa-cdn-besucher-{stempel}"
    docker("run", "-d", "--name", besucher, "--network", netz, "--entrypoint", "sleep", IMAGE, "300")
    namen.append(besucher)
    selbst = ip(besucher)
    for name in (ohne, mit, pflicht, kurz):   # bereit, sobald Caddy antwortet (kein fester Wartewert)
        for _ in range(100):
            if abruf(name, "/", {"X-Stafl-Cdn": SCHLUESSEL})[0]:
                break
            time.sleep(0.1)
    cdn = {"X-Stafl-Cdn": SCHLUESSEL, "X-Real-IP": ECHT}

    code, kopf, inhalt = abruf(ohne, "/", {"X-Real-IP": FALSCH, "X-Forwarded-For": FALSCH})
    check("ohne Schlüssel: Besucher-IP ist die Verbindung, gefälschte Köpfe zählen nicht", code == 200 and f"xff=[{selbst}]" in inhalt, (code, inhalt))
    code, kopf, inhalt = abruf(ohne, "/", {"X-Stafl-Cdn": "", "X-Real-IP": FALSCH})
    check("ohne Schlüssel: leerer Kopf „X-Stafl-Cdn“ öffnet nichts, Sperre bleibt aus", code == 200 and f"xff=[{selbst}]" in inhalt and "Stafl-Cdn: erkannt" not in kopf, (code, inhalt))

    code, kopf, inhalt = abruf(mit, "/", cdn)
    check("mit Schlüssel über bunny: Besucher-IP von bunny (X-Real-IP)", code == 200 and f"xff=[{ECHT}]" in inhalt, (code, inhalt))
    check("mit Schlüssel über bunny: Anwendung bekommt den Schlüssel nie", "cdn=[]" in inhalt and SCHLUESSEL not in inhalt, inhalt)
    check("mit Schlüssel über bunny: Antwortkopf „Stafl-Cdn: erkannt“", "Stafl-Cdn: erkannt" in kopf, kopf[-300:])
    code, kopf, inhalt = abruf(mit, "/anmeldung/seite", cdn)
    check("mit Schlüssel: auch im eigenen handle-Block (Anmeldung) die Besucher-IP von bunny", code == 200 and f"xff=[{ECHT}]" in inhalt, (code, inhalt))
    code, kopf, inhalt = abruf(mit, "/", {"X-Stafl-Cdn": SCHLUESSEL[:-1] + "x", "X-Real-IP": FALSCH})
    check("falscher Schlüssel: wie ohne CDN (IP nicht fälschbar), kein „erkannt“", code == 200 and f"xff=[{selbst}]" in inhalt and "Stafl-Cdn" not in kopf, (code, inhalt))
    code, kopf, inhalt = abruf(mit, "/", {"X-Real-IP": FALSCH})
    check("ohne Sperre: direkte Anfrage weiter erlaubt", code == 200 and f"xff=[{selbst}]" in inhalt, (code, inhalt))
    for wert in ("kaputt", f"{ECHT}, {FALSCH}", "", "10.0.0.1/8", "1.2.3"):
        code, kopf, inhalt = abruf(mit, "/", {"X-Stafl-Cdn": SCHLUESSEL, "X-Real-IP": wert})
        check(f"mit Schlüssel, X-Real-IP „{wert}“ keine einzelne Adresse: Verbindung zählt, kein „erkannt“", code == 200 and f"xff=[{selbst}]" in inhalt
              and "Stafl-Cdn: erkannt" not in kopf, (code, inhalt))
    code, kopf, inhalt = abruf(mit, "/", {"X-Stafl-Cdn": SCHLUESSEL, "X-Real-IP": "2001:db8::7"})
    check("mit Schlüssel: IPv6-Besucher von bunny übernommen", code == 200 and "xff=[2001:db8::7]" in inhalt, (code, inhalt))

    code, kopf, inhalt = abruf(pflicht, "/")
    check("Sperre: direkte Anfrage 403", code == 403, (code, kopf[-200:]))
    code, kopf, inhalt = abruf(pflicht, "/anmeldung/seite")
    check("Sperre: gilt auch vor anderen handle-Blöcken (Anmeldung)", code == 403, code)
    code, kopf, inhalt = abruf(pflicht, "/", {"X-Stafl-Cdn": "falsch", "X-Real-IP": FALSCH})
    check("Sperre: falscher Schlüssel 403", code == 403, code)
    code, kopf, inhalt = abruf(pflicht, "/", cdn)
    check("Sperre: über bunny durch, mit Besucher-IP", code == 200 and f"xff=[{ECHT}]" in inhalt, (code, inhalt))
    code, kopf, inhalt = abruf(pflicht, "/", {"X-Stafl-Cdn": SCHLUESSEL, "X-Real-IP": "kaputt"})
    check("Sperre: mit Schlüssel, aber ohne gültige Besucher-IP durch (Adresse der Verbindung)", code == 200 and f"xff=[{selbst}]" in inhalt, (code, inhalt))

    code, kopf, inhalt = abruf(kurz, "/", {"X-Stafl-Cdn": "kurz1234", "X-Real-IP": FALSCH})
    check("zu kurzer Schlüssel: nie vertraut und keine Sperre", code == 200 and f"xff=[{selbst}]" in inhalt and "Stafl-Cdn" not in kopf, (code, inhalt))

    hp = docker("port", server, "8080").stdout.split()
    basis = f"http://{hp[0]}" if hp else ""
    oeffner = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def vom_server(kopf=None):
        anfrage = urllib.request.Request(basis + "/", headers=kopf or {})
        for _ in range(100):
            try:
                return oeffner.open(anfrage, timeout=5).status
            except urllib.error.HTTPError as e:
                return e.code
            except OSError:
                time.sleep(0.1)
        return 0
    code = vom_server()
    check("Sperre: Abruf vom Server selbst ohne Schlüssel 403 (Docker-Weiterleitung erscheint privat – wie Besucher über IPv6)", code == 403, code)
    code = vom_server({"X-Stafl-Cdn": SCHLUESSEL})
    check("Sperre: Abruf vom Server selbst mit Schlüssel erlaubt", code == 200, code)
    # die Funktion des Einspielskripts unverändert: Schlüssel über curl -K - (Konfiguration auf der Standardeingabe)
    r = subprocess.run(["sh", "-c", pruefabruf + '\npruefabruf -s -o /dev/null -w "%{http_code}" --noproxy "*" "$1"', "sh", basis + "/"],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin:/usr/local/bin", "CDN_KEY": SCHLUESSEL})
    check("Prüfung nach dem Einspielen (pruefabruf) kommt mit dem Schlüssel durch", r.stdout.strip() == "200", (r.stdout, r.stderr[-200:]))
    r = subprocess.run(["sh", "-c", pruefabruf + '\npruefabruf -s -o /dev/null -w "%{http_code}" --noproxy "*" "$1"', "sh", basis + "/"],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin:/usr/local/bin", "CDN_KEY": ""})
    check("ohne Schlüssel in .env: pruefabruf wie bisher ohne Kopf (hier 403)", r.stdout.strip() == "403", r.stdout)
finally:
    if not all(res):
        for n in namen[:5]:
            print(n, docker("logs", "--tail", "8", n, pruefen=False).stderr[-600:])
    for n in namen:
        docker("rm", "-f", n, pruefen=False)
    docker("network", "rm", netz, pruefen=False)
    shutil.rmtree(arbeit, ignore_errors=True)

print(f"\n{sum(res)}/{len(res)} bestanden")
sys.exit(0 if all(res) else 1)
