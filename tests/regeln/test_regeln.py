#!/usr/bin/env python3
"""Tests für werkzeuge/regeln.py: das echte Regelwerk ist stimmig, und typische Verstöße werden erkannt.

Aufruf: python3 tests/regeln/test_regeln.py   (nur Standardbibliothek)
Jeder Negativtest baut ein kleines künstliches Projekt in einem Temp-Ordner und verändert genau eine Stelle.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WURZEL / "werkzeuge"))
import regeln  # noqa: E402

WARTUNG = (WURZEL / "regeln/wartung.toml").read_text(encoding="utf-8")

MODULE = """
schema = 1
[dashboard]
pflichtmodule = ["angebot", "lager"]

[[modul]]
id = "angebot"
name = "Angebot"
beschreibung = "x"
icon = "tag"
reihenfolge = 10
dashboard = true
agent = "angebot"
abhaengigkeiten = ["plattform", "lager"]
testgruppen = ["frontend"]
pfade = ["app/api/lib/angebote.php", "tests/e2e/test_frontend.py"]
pfade_geplant = ["app/api/module/angebot/**"]
  [[modul.oberflaeche]]
  id = "kunden"
  name = "Kunden"
  art = "extern"
  adresse = "https://angebot.example/"
  entwicklung = "fertig"
  freigabe = "produktiv"
  sperrbar = true
  [[modul.oberflaeche]]
  id = "eingabe"
  name = "Eingabe"
  art = "intern"
  adresse = "https://angebot.example/eingabe/"
  entwicklung = "fertig"
  freigabe = "produktiv"
  sperrbar = true

[[modul]]
id = "lager"
name = "Lager"
beschreibung = "x"
icon = "boxes"
reihenfolge = 20
dashboard = true
agent = "lager"
abhaengigkeiten = ["plattform"]
testgruppen = ["stock"]
pfade = ["app/api/lib/bestand.php"]
pfade_geplant = []
  [[modul.oberflaeche]]
  id = "intern"
  name = "Lager"
  art = "intern"
  adresse = "https://lager.dashboard-stafl.de/"
  entwicklung = "geplant"
  freigabe = "keine"
  sperrbar = true

[[modul]]
id = "verwaltung"
name = "Verwaltung"
beschreibung = "x"
icon = "settings"
dashboard = false
agent = "verwaltung"
abhaengigkeiten = ["plattform"]
testgruppen = []
pfade = []
pfade_geplant = []
  [[modul.oberflaeche]]
  id = "system"
  name = "System"
  art = "intern"
  adresse = "https://verwaltung.dashboard-stafl.de/system/"
  entwicklung = "geplant"
  freigabe = "keine"
  sperrbar = false

[[modul]]
id = "dashboard"
name = "Dashboard"
beschreibung = "x"
icon = "grid"
dashboard = false
agent = "dashboard"
abhaengigkeiten = ["plattform"]
testgruppen = []
pfade = []
pfade_geplant = []
  [[modul.oberflaeche]]
  id = "start"
  name = "Start"
  art = "intern"
  adresse = "https://dashboard-stafl.de/"
  entwicklung = "geplant"
  freigabe = "keine"
  sperrbar = false

[[modul]]
id = "plattform"
name = "Kern"
beschreibung = "x"
icon = "cpu"
dashboard = false
agent = "plattform"
abhaengigkeiten = []
testgruppen = ["users"]
pfade = ["app/api/lib/**", "regeln/**", "tests/**", "AGENTS.md", "Caddyfile", ".github/**"]
pfade_geplant = []

[[koordination]]
bereich = "Rechte"
pfade = ["app/api/lib/rechte.php"]
"""

DATEN = """
schema = 1
[[dokument]]
name = "angebot"
eigentuemer = "angebot"
schutz = "oeffentlich"
beschreibung = "x"

[[dokument]]
name = "bestand"
eigentuemer = "lager"
leser = ["angebot"]
schutz = "vertraulich"
beschreibung = "x"

[[dokument]]
name = "protokoll/*"
eigentuemer = "plattform"
schutz = "vertraulich"
beschreibung = "x"
"""

RECHTE = """
schema = 1
[zuordnung]
"angebot.bearbeiten" = "angebot"
"bestand.sehen" = "lager"
"""

KATALOG = """
schema = 1
[[regel]]
id = "GR-001"
titel = "Keine Mengen öffentlich"
beschreibung = "x"
verantwortlich = "angebot"
module = ["angebot", "lager"]
daten = ["bestand"]
tests = ["e2e:frontend", "ci:Secret-Scan", "datei:tests/e2e/test_frontend.py"]
quelle = "AGENTS.md"
status = "verbindlich"
version = 1
seit = "2026-10-21"
"""

DATEIEN = {
    "AGENTS.md": "Regel GR-001 gilt.\n",
    "Caddyfile": textwrap.dedent("""\
        {$DOMAIN} {
        \treverse_proxy app:80
        }

        dashboard-stafl.de, lager.dashboard-stafl.de, verwaltung.dashboard-stafl.de {
        \theader {
        \t\tCache-Control "no-store"
        \t}
        \trespond "In Vorbereitung." 503
        }
        """),
    ".github/workflows/ci.yml": "jobs:\n  a:\n    steps:\n      - name: Secret-Scan\n        run: echo\n",
    "tests/run_e2e.py": "SUITES = {\n    'frontend': (1, 'a', False),\n    'stock': (1, 'a', False),\n}\nSUITES['users'] = SUITES['stock']\n",
    "tests/e2e/test_frontend.py": "# Test\n",
    "app/api/lib/rechte.php": "<?php\nconst PERMS = [\n    'angebot.bearbeiten' => ['g' => 'A'],\n    'bestand.sehen' => ['g' => 'B'],\n];\n",
    "app/api/lib/angebote.php": "<?php\n$a = store_read('angebot');\nstore_write('angebot', $a);\n$b = store_read('bestand');\n",
    "app/api/lib/bestand.php": "<?php\nwith_lock('bestand', function () { store_write('bestand', []); });\n",
    "app/api/lib/protokoll.php": "<?php\nstore_write('protokoll/' . $monat, []);\n",
}


class Projekt:
    """Künstliches Projekt im Temp-Ordner; ersetzen() ändert genau eine Stelle."""

    def __init__(self):
        self.wurzel = Path(tempfile.mkdtemp(prefix="regeln-test-"))
        texte = dict(DATEIEN)
        texte.update({"regeln/module.toml": MODULE, "regeln/datenverantwortung.toml": DATEN,
                      "regeln/berechtigungen.toml": RECHTE, "regeln/katalog.toml": KATALOG,
                      "regeln/wartung.toml": WARTUNG})
        for pfad, text in texte.items():
            self.schreiben(pfad, text)

    def schreiben(self, pfad: str, text: str) -> None:
        p = self.wurzel / pfad
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def ersetzen(self, pfad: str, alt: str, neu: str) -> None:
        p = self.wurzel / pfad
        text = p.read_text(encoding="utf-8")
        assert alt in text, f"{alt!r} nicht in {pfad}"
        p.write_text(text.replace(alt, neu, 1), encoding="utf-8")

    def fehler(self) -> list:
        return regeln.pruefen(regeln.laden(self.wurzel)).fehler

    def entfernen(self) -> None:
        shutil.rmtree(self.wurzel, ignore_errors=True)


class EchtesRegelwerk(unittest.TestCase):
    def test_repository_ist_stimmig(self):
        rw = regeln.pruefen(regeln.laden(WURZEL))
        self.assertEqual(rw.fehler, [], "\n".join(rw.fehler))

    def test_acht_pflichtmodule_im_dashboard(self):
        rw = regeln.laden(WURZEL)
        kacheln = [m["id"] for m in rw.modulliste if m.get("dashboard")]
        self.assertEqual(set(kacheln), {"angebot", "bestand", "crm", "rewe", "qs", "einkauf", "import", "verwaltung"})
        self.assertEqual(rw.modul("import")["teil_von"], "verwaltung")
        self.assertEqual(rw.modul("import")["kachel_ziel"], "verwaltung.import")
        self.assertEqual(rw.modul("angebot")["kachel_ziel"], "eingabe")

    def test_unfertige_module_nicht_freigegeben(self):
        rw = regeln.laden(WURZEL)
        for mid in ("bestand", "crm", "rewe", "qs", "einkauf", "verwaltung", "dashboard"):
            for o in rw.modul(mid).get("oberflaeche", []):
                self.assertEqual(o["freigabe"], "keine", f"{mid}.{o['id']}")

    def test_angebot_kunden_und_eingabe_getrennt(self):
        o = {x["id"]: x for x in regeln.laden(WURZEL).modul("angebot")["oberflaeche"]}
        self.assertEqual(o["kunden"]["art"], "extern")
        self.assertEqual(o["eingabe"]["art"], "intern")
        self.assertEqual(o["eingabe"]["adresse"], "https://angebot-stafl.de/admin/")
        self.assertEqual(o["eingabe"]["ziel"], "https://angebot.dashboard-stafl.de/")

    def test_adr003_hosts_und_regeln(self):
        rw = regeln.laden(WURZEL)
        anm = {o["id"]: o for o in rw.modul("plattform")["oberflaeche"]}["anmeldung"]
        self.assertEqual(anm["adresse"], "https://login.dashboard-stafl.de/")
        self.assertIs(anm["sperrbar"], False)
        self.assertEqual(anm["freigabe"], "keine")
        ids = {r["id"] for r in rw.katalog["regel"]}
        self.assertTrue({"GR-108", "GR-109", "GR-110", "GR-111"} <= ids)

    def test_entscheidungstabelle_vollstaendig(self):
        w = regeln.laden(WURZEL).wartung
        lagen = list(regeln.alle_lagen(w))
        self.assertEqual(len(lagen), 4 * 4 * 2 * 3)
        for lage in lagen:
            self.assertIsNotNone(regeln.entscheiden(w, lage), lage)

    def test_wartung_beenden_macht_nichts_produktiv(self):
        w = regeln.laden(WURZEL).wartung
        for e in w["werte"]["entwicklung"]:
            for p in w["werte"]["person"]:
                lage = {"entwicklung": e, "freigabe": "keine", "betrieb": "normal", "person": p}
                self.assertFalse(regeln.entscheiden(w, lage)["zugang"], lage)

    def test_folgen_fuer_rechte_aenderung(self):
        e = regeln.folgen(regeln.laden(WURZEL), ["app/api/lib/rechte.php"])
        self.assertEqual(e["module"], ["plattform"])
        self.assertIn("Nutzer, Rechte und Sicherheit", e["koordination"])
        self.assertTrue(e["volle_suite_noetig"])
        self.assertIn("users", e["testgruppen"])

    def test_folgen_fuer_bestand(self):
        e = regeln.folgen(regeln.laden(WURZEL), ["app/api/lib/bestand.php"])
        self.assertEqual(e["module"], ["bestand"])
        self.assertIn("stock", e["testgruppen"])
        self.assertIn("angebot", e["abhaengige_module"])
        self.assertFalse(e["volle_suite_noetig"])
        self.assertIn("GR-001", [r["id"] for r in e["regeln"]])


class Verstoesse(unittest.TestCase):
    def setUp(self):
        self.p = Projekt()

    def tearDown(self):
        self.p.entfernen()

    def assertFehler(self, teiltext: str):
        f = self.p.fehler()
        self.assertTrue(any(teiltext in x for x in f), f"„{teiltext}“ nicht unter den Fehlern:\n" + "\n".join(f))

    def test_grundprojekt_ist_stimmig(self):
        self.assertEqual(self.p.fehler(), [])

    def test_datei_ohne_eigentuemer(self):
        self.p.schreiben("app/neu.js", "// neu\n")
        self.assertFehler("Datei ohne Eigentümer: app/neu.js")

    def test_mehrdeutige_zuordnung(self):
        self.p.ersetzen("regeln/module.toml", 'pfade = ["app/api/lib/bestand.php"]',
                        'pfade = ["app/api/lib/bestand.php", "app/api/lib/angebote.php"]')
        self.assertFehler("mehrdeutig")

    def test_unregistriertes_dokument(self):
        self.p.schreiben("app/api/lib/neu.php", "<?php\nstore_write('geheimliste', []);\n")
        self.assertFehler("„geheimliste“, das nicht in regeln/datenverantwortung.toml steht")

    def test_fremdes_dokument_schreiben(self):
        self.p.ersetzen("app/api/lib/angebote.php", "store_write('angebot', $a);", "store_write('bestand', $a);")
        self.assertFehler("(Modul angebot) schreibt „bestand“ von lager ohne Eintrag unter schreiber")
        self.p.ersetzen("regeln/datenverantwortung.toml", 'leser = ["angebot"]', 'schreiber = ["angebot"]')
        self.assertEqual([x for x in self.p.fehler() if "schreibt" in x], [])

    def test_fremdes_dokument_lesen(self):
        self.p.ersetzen("regeln/datenverantwortung.toml", 'leser = ["angebot"]\n', "")
        self.assertFehler("(Modul angebot) liest „bestand“ von lager ohne Eintrag unter leser")

    def test_verwaistes_dokument(self):
        self.p.ersetzen("regeln/datenverantwortung.toml", 'name = "angebot"', 'name = "alt"')
        self.assertFehler("Dokument alt wird im Code nicht (mehr) verwendet")

    def test_produktiv_ohne_fertigen_code(self):
        self.p.ersetzen("regeln/module.toml", 'entwicklung = "geplant"\n  freigabe = "keine"\n  sperrbar = true',
                        'entwicklung = "geplant"\n  freigabe = "produktiv"\n  sperrbar = true')
        self.assertFehler("Freigabe „produktiv“ ist bei Entwicklungsstand „geplant“ nicht zulässig")

    def test_aussperrschutz(self):
        self.p.ersetzen("regeln/module.toml", "sperrbar = false", "sperrbar = true")
        self.assertFehler("muss sperrbar = false haben")

    def test_teil_von_ohne_eigene_implementierung(self):
        self.p.ersetzen("regeln/module.toml", 'id = "verwaltung"', 'id = "verwaltung"\nteil_von = "plattform"')
        self.assertFehler("keine eigenen Pfade/Oberflächen")

    def test_kreis_in_abhaengigkeiten(self):
        self.p.ersetzen("regeln/module.toml", 'abhaengigkeiten = ["plattform"]\ntestgruppen = ["stock"]',
                        'abhaengigkeiten = ["angebot"]\ntestgruppen = ["stock"]')
        self.assertFehler("Kreis in den Modulabhängigkeiten")

    def test_recht_ohne_modul(self):
        self.p.ersetzen("app/api/lib/rechte.php", "];", "    'lohn.sehen' => ['g' => 'L'],\n];")
        self.assertFehler("Recht lohn.sehen ist keinem Modul zugeordnet")

    def test_recht_mit_modulpraefix_braucht_keinen_eintrag(self):
        self.p.ersetzen("app/api/lib/rechte.php", "];", "    'lager.zaehlen' => ['g' => 'L'],\n];")
        self.assertEqual(self.p.fehler(), [])

    def test_veraltete_rechtezuordnung(self):
        self.p.ersetzen("regeln/berechtigungen.toml", '"bestand.sehen" = "lager"', '"bestand.sehen" = "lager"\n"weg.recht" = "lager"')
        self.assertFehler("Recht weg.recht gibt es in rechte.php nicht")

    def test_unbekannte_regel_in_agents(self):
        self.p.schreiben("AGENTS.md", "Regel GR-001 und GR-999.\n")
        self.assertFehler("AGENTS.md nennt GR-999")

    def test_regel_fehlt_in_agents(self):
        self.p.schreiben("AGENTS.md", "keine Kennungen\n")
        self.assertFehler("Regel GR-001 (quelle AGENTS.md) wird in AGENTS.md nicht genannt")

    def test_regel_mit_unbekanntem_test(self):
        self.p.ersetzen("regeln/katalog.toml", '"e2e:frontend"', '"e2e:gibtsnicht"')
        self.assertFehler("E2E-Gruppe „gibtsnicht“ gibt es nicht")

    def test_verbindliche_regel_ohne_tests(self):
        self.p.ersetzen("regeln/katalog.toml", 'tests = ["e2e:frontend", "ci:Secret-Scan", "datei:tests/e2e/test_frontend.py"]',
                        "tests = []")
        self.assertFehler("verbindliche Regel ohne Tests")

    def test_testgruppe_ohne_modul(self):
        self.p.ersetzen("tests/run_e2e.py", "SUITES['users']", "SUITES['neu'] = SUITES['stock']\nSUITES['users']")
        self.assertFehler("E2E-Gruppe „neu“ ist keinem Modul zugeordnet")

    def test_tabelle_unvollstaendig(self):
        w = self.p.wurzel / "regeln/wartung.toml"
        w.write_text(w.read_text(encoding="utf-8").replace('wenn = { freigabe = "produktiv" }', 'wenn = { freigabe = "produktiv", person = "tester" }'),
                     encoding="utf-8")
        self.assertFehler("Entscheidungstabelle unvollständig")

    def test_falsche_reihenfolge_verletzt_invariante(self):
        # Administrator-Ausnahme vor „keine Freigabe“: Wartung würde ein unfertiges Modul öffnen.
        self.p.ersetzen("regeln/wartung.toml", "nr = 3\n", "nr = 30\n")
        self.p.ersetzen("regeln/wartung.toml", "nr = 5\n", "nr = 3\n")
        self.assertFehler("Invariante „Ohne Freigabe kein Zugang – unabhängig von Wartung“ verletzt")

    def test_testfall_falsch(self):
        self.p.ersetzen("regeln/wartung.toml", 'erwartet = { zugang = false, http = 503, kachel = "wartung" }',
                        'erwartet = { zugang = true, http = 503, kachel = "wartung" }')
        self.assertFehler("Testfall „CRM in Wartung, normaler Nutzer“")

    def test_dashboard_host_ohne_platzhalter(self):
        self.p.ersetzen("Caddyfile", '\trespond "In Vorbereitung." 503\n', "\treverse_proxy app:80\n")
        self.assertFehler("lager.dashboard-stafl.de: keine Oberfläche freigegeben, Caddy muss den 503-Platzhalter liefern")

    def test_unbekannter_dashboard_host(self):
        self.p.ersetzen("Caddyfile", "verwaltung.dashboard-stafl.de {", "verwaltung.dashboard-stafl.de, lohn.dashboard-stafl.de {")
        self.assertFehler("lohn.dashboard-stafl.de ist weder Oberfläche noch Umgebung")

    def test_externe_oberflaeche_nicht_unter_dashboard(self):
        self.p.ersetzen("regeln/module.toml", 'adresse = "https://angebot.example/"',
                        'adresse = "https://portal.dashboard-stafl.de/"')
        self.assertFehler("externe Oberflächen dürfen nicht unter dashboard-stafl.de liegen")

    def test_host_ohne_dns_darf_im_caddyfile_fehlen(self):
        self.p.ersetzen("regeln/module.toml", 'adresse = "https://lager.dashboard-stafl.de/"',
                        'adresse = "https://neu.dashboard-stafl.de/"\n  dns = false')
        self.p.ersetzen("Caddyfile", "dashboard-stafl.de, lager.dashboard-stafl.de,", "dashboard-stafl.de,")
        self.assertEqual(self.p.fehler(), [])

    def test_host_ohne_dns_nicht_freigeben(self):
        self.p.ersetzen("regeln/module.toml", 'adresse = "https://lager.dashboard-stafl.de/"\n  entwicklung = "geplant"\n  freigabe = "keine"',
                        'adresse = "https://neu.dashboard-stafl.de/"\n  dns = false\n  entwicklung = "geplant"\n  freigabe = "deaktiviert"')
        self.assertFehler("ohne DNS-Eintrag (dns = false) ist nur freigabe")

    def test_veralteter_dns_vermerk(self):
        self.p.ersetzen("regeln/module.toml", 'adresse = "https://lager.dashboard-stafl.de/"',
                        'adresse = "https://lager.dashboard-stafl.de/"\n  dns = false')
        self.assertFehler("als dns = false vermerkt")

    def test_externes_ziel_nicht_unter_dashboard(self):
        self.p.ersetzen("regeln/module.toml", 'adresse = "https://angebot.example/"',
                        'adresse = "https://angebot.example/"\n  ziel = "https://kunden.dashboard-stafl.de/"')
        self.assertFehler("externe Oberflächen dürfen nicht unter dashboard-stafl.de liegen")

    def test_ziel_host_im_caddyfile_erlaubt(self):
        self.p.ersetzen("regeln/module.toml", 'adresse = "https://angebot.example/eingabe/"',
                        'adresse = "https://angebot.example/eingabe/"\n  ziel = "https://angebot.dashboard-stafl.de/"')
        self.p.ersetzen("Caddyfile", "verwaltung.dashboard-stafl.de {", "verwaltung.dashboard-stafl.de, angebot.dashboard-stafl.de {")
        self.assertEqual(self.p.fehler(), [])

    def test_folgen_im_kleinen(self):
        rw = regeln.laden(self.p.wurzel)
        e = regeln.folgen(rw, ["app/api/lib/bestand.php"])
        self.assertEqual(e["module"], ["lager"])
        self.assertEqual(e["abhaengige_module"], ["angebot"])
        self.assertEqual(e["dokumente"], ["bestand"])
        self.assertIn("angebot", e["daten_mitbetroffen"])
        self.assertEqual([r["id"] for r in e["regeln"]], ["GR-001"])
        self.assertEqual(e["testgruppen"], ["frontend", "stock"])
        self.assertIn("ci:Secret-Scan", e["weitere_pruefungen"])
        e = regeln.folgen(rw, ["app/api/lib/rechte.php"])
        self.assertEqual(list(e["koordination"]), ["Rechte"])
        self.assertTrue(e["volle_suite_noetig"])


class Muster(unittest.TestCase):
    def test_platzhalter(self):
        self.assertTrue(regeln.passt("app/admin/**", "app/admin/a/b.html"))
        self.assertTrue(regeln.passt("tests/e2e/test_order_*.py", "tests/e2e/test_order_outbox_ui.py"))
        self.assertFalse(regeln.passt("app/assets/*", "app/assets/fonts/a.woff2"))
        self.assertFalse(regeln.passt("app/api/lib/kern.php", "app/api/lib/kern.php.bak"))

    def test_genauigkeit(self):
        self.assertGreater(regeln.genauigkeit("app/api/lib/bestand.php"), regeln.genauigkeit("app/api/lib/**"))
        self.assertGreater(regeln.genauigkeit("tests/e2e/test_order_*.py"), regeln.genauigkeit("tests/**"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
