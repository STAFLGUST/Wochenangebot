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
pfade = ["app/api/lib/angebote.php", "tests/e2e/test_frontend.py", "app/api/aktionen/demo.php", "regeln/aktionen/angebot.toml"]
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
    "app/api/aktionen/demo.php": "<?php\nswitch ($action) {\n    case 'offer': respond([]);\n    case 'save_draft': respond([]);\n}\n",
    "regeln/aktionen/angebot.toml": textwrap.dedent("""\
        schema = 1
        modul = "angebot"

        [aktion.offer]
        oberflaeche = "angebot.kunden"
        oeffentlich = true
        kunden_wartung = true

        [aktion.save_draft]
        oberflaeche = "angebot.eingabe"
        schreibend = true
        """),
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
        self.erzeugen()

    def erzeugen(self) -> None:
        self.schreiben(regeln.AKTIONEN_LISTE, regeln.aktionen_php(regeln.laden(self.wurzel)))

    def erzeugen_module(self) -> None:
        self.schreiben(regeln.MODULE_LISTE, regeln.module_php(regeln.laden(self.wurzel)))

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


# Stand vor dem Aktionsregister (app/api/index.php, main 39483ff) – darf sich für diese Aktionen nicht unbemerkt ändern.
ALT_SCHREIBEND = {
    'benachrichtigung_save', 'benachrichtigung_test', 'bestell_settings_save', 'bestellung_mail_retry',
    'bestellung_save', 'change_password', 'discard_draft', 'draft_ping', 'einkauf_melden', 'einzel_loeschen',
    'einzel_save', 'einzel_senden', 'einzel_status', 'fracht_save', 'fw_feed_update', 'fw_freigeben',
    'fw_import', 'fw_save', 'fw_sperren', 'fw_vorlage', 'geo_clear_stats', 'geo_update', 'history_delete',
    'history_import', 'ip_unblock', 'kunde_abmelden', 'kunde_abmelden_info', 'kunde_bestellung', 'kunde_delete',
    'kunde_login', 'kunde_logout', 'kunde_mail', 'kunde_merkliste_save', 'kunde_passwort', 'kunde_save',
    'kunde_token_check', 'kunde_token_set', 'kunden_import', 'kunden_mail_vorschau', 'kunden_restposten',
    'kunden_rundmail', 'kundengruppen_save', 'login', 'login_2fa', 'logout', 'mail_konto_save', 'mail_save',
    'mail_test', 'master_save', 'offers_save', 'ort_update', 'passkey_begin', 'passkey_delete', 'passkey_login',
    'passkey_login_begin', 'passkey_register', 'passkey_rename', 'publish', 'reauth', 'rechte_save',
    'save_draft', 'security_diag', 'security_export', 'security_save', 'session_end', 'setup', 'stock_import',
    'stock_pdf', 'twofa_begin', 'twofa_disable', 'twofa_enable', 'user_delete', 'user_mail', 'user_save',
    'user_unlock', 'vertreter_save', 'vkgruppen_save', 'wartung_save',
}
ALT_OEFFENTLICH = {
    'abmelden1', 'app_info', 'kunde_abmelden', 'kunde_abmelden_info', 'kunde_bestellung',
    'kunde_bestellung_detail', 'kunde_bestellungen', 'kunde_login', 'kunde_logout', 'kunde_merkliste',
    'kunde_merkliste_save', 'kunde_passwort', 'kunde_status', 'kunde_token_check', 'kunde_token_set', 'offer',
    'waf_probe',
}
ALT_WARTUNG = {
    'kunde_bestellung', 'kunde_bestellung_detail', 'kunde_bestellungen', 'kunde_login', 'kunde_merkliste',
    'kunde_merkliste_save', 'kunde_passwort', 'kunde_token_check', 'kunde_token_set', 'offer',
}

ALT_ALLE = {  # alle 122 Aktionen vor dem Register; neue Aktionen sind von diesem Vergleich ausgenommen
    'abmelden1', 'app_info', 'auswertung', 'benachrichtigung_save', 'benachrichtigung_test',
    'bestell_settings_save', 'bestellung', 'bestellung_mail_retry', 'bestellung_save', 'bestellungen',
    'change_password', 'discard_draft', 'draft', 'draft_ping', 'einkauf', 'einkauf_melden', 'einzel_artikel',
    'einzel_detail', 'einzel_liste', 'einzel_loeschen', 'einzel_pdf', 'einzel_save', 'einzel_senden',
    'einzel_status', 'fracht_save', 'fw_export', 'fw_feed_update', 'fw_freigeben', 'fw_import', 'fw_save',
    'fw_sperren', 'fw_status', 'fw_verkehr', 'fw_vorlage', 'geo_clear_stats', 'geo_lookup', 'geo_update',
    'history_data', 'history_delete', 'history_import', 'history_list', 'history_prev', 'ip_unblock',
    'kunde_abmelden', 'kunde_abmelden_info', 'kunde_bestellung', 'kunde_bestellung_detail',
    'kunde_bestellungen', 'kunde_delete', 'kunde_login', 'kunde_logout', 'kunde_mail', 'kunde_merkliste',
    'kunde_merkliste_save', 'kunde_passwort', 'kunde_save', 'kunde_status', 'kunde_token_check',
    'kunde_token_set', 'kunden', 'kunden_import', 'kunden_mail_vorschau', 'kunden_restposten',
    'kunden_rundmail', 'kundengruppen', 'kundengruppen_save', 'log', 'login', 'login_2fa', 'logout',
    'mail_info', 'mail_konto_save', 'mail_save', 'mail_status', 'mail_test', 'master', 'master_save', 'offer',
    'offers', 'offers_save', 'ort_update', 'passkey_begin', 'passkey_delete', 'passkey_list', 'passkey_login',
    'passkey_login_begin', 'passkey_register', 'passkey_rename', 'publish', 'reauth', 'rechte', 'rechte_save',
    'restposten_info', 'save_draft', 'security_diag', 'security_export', 'security_integrity', 'security_save',
    'security_status', 'session_end', 'setup', 'status', 'stock', 'stock_import', 'stock_pdf', 'testpostfach',
    'twofa_begin', 'twofa_disable', 'twofa_enable', 'user_delete', 'user_mail', 'user_save', 'user_unlock',
    'users', 'version', 'versions', 'vertreter', 'vertreter_save', 'vkgruppen', 'vkgruppen_save', 'waf_probe',
    'wartung_save',
}

class EchtesRegelwerk(unittest.TestCase):
    def test_aktionen_wie_vor_dem_register(self):
        """Schreibschutz, öffentlicher Bereich und Wartung bleiben für alle bisherigen Aktionen unverändert."""
        tab = {a: x for a, x in regeln.aktionen_tabelle(regeln.laden(WURZEL)).items() if a in ALT_ALLE}
        self.assertEqual(set(tab), ALT_ALLE, "eine bisherige Aktion fehlt im Register")
        self.assertEqual({a for a, x in tab.items() if x["schreibend"] is True}, ALT_SCHREIBEND)
        self.assertEqual({a for a, x in tab.items() if x["schreibend"] == "post"}, {"security_integrity"})
        self.assertEqual({a for a, x in tab.items() if x["oeffentlich"]}, ALT_OEFFENTLICH)
        self.assertEqual({a for a, x in tab.items() if x["kunden_wartung"]}, ALT_WARTUNG)

    def test_php_tabelle_entscheidet_wie_die_pruefung(self):
        """Vertragstest GR-102: lib/module.php wertet die erzeugte Tabelle für alle Kombinationen genauso aus wie
        werkzeuge/regeln.py – und erfüllt die Testfälle aus regeln/wartung.toml."""
        import json, subprocess
        rw = regeln.laden(WURZEL)
        lagen = list(regeln.alle_lagen(rw.wartung)) + [t["eingabe"] for t in rw.wartung["testfall"]]
        php = ("define('WA_API', 1); require $argv[1]; require $argv[2]; $out = [];"
               "foreach (json_decode($argv[3], true) as $l) $out[] = modul_entscheiden($l); echo json_encode($out);")
        r = subprocess.run(["php", "-r", php, str(WURZEL / "app/api/lib/module-liste.php"), str(WURZEL / "app/api/lib/module.php"),
                            json.dumps(lagen)], capture_output=True, text=True, check=True)
        ergebnisse = json.loads(r.stdout)
        self.assertEqual(len(ergebnisse), len(lagen))
        for lage, ph in zip(lagen, ergebnisse):
            py = regeln.entscheiden(rw.wartung, lage)
            self.assertEqual((ph["nr"], ph["zugang"], ph["http"], ph["kachel"]), (py["nr"], py["zugang"], py["http"], py["kachel"]), lage)
        for t, ph in zip(rw.wartung["testfall"], ergebnisse[-len(rw.wartung["testfall"]):]):
            for k, v in t["erwartet"].items():
                self.assertEqual(ph[k], v, t["name"])

    def test_module_liste_erzeugt_und_ohne_interna(self):
        rw = regeln.laden(WURZEL)
        text = (WURZEL / regeln.MODULE_LISTE).read_text(encoding="utf-8")
        self.assertEqual(text, regeln.module_php(rw))
        for intern in ("pfade", "agent", "hinweise", "testgruppen", "app/api/"):
            self.assertNotIn(intern, text, intern)

    def test_aktionen_vollstaendig_und_erzeugt(self):
        rw = regeln.laden(WURZEL)
        self.assertEqual(set(regeln.aktionen_tabelle(rw)), regeln.aktionen_im_code(WURZEL))
        self.assertEqual((WURZEL / regeln.AKTIONEN_LISTE).read_text(encoding="utf-8"), regeln.aktionen_php(rw))
        self.assertGreater(len(regeln.aktionen_tabelle(rw)), 100)

    def test_repository_ist_stimmig(self):
        rw = regeln.pruefen(regeln.laden(WURZEL))
        self.assertEqual(rw.fehler, [], "\n".join(rw.fehler))

    def test_acht_pflichtmodule_im_dashboard(self):
        rw = regeln.laden(WURZEL)
        kacheln = [m["id"] for m in rw.modulliste if m.get("dashboard")]
        # Startumfang (Pflichtmodule) plus die vom Inhaber angelegten Module HR, Marketing, Controlling, Sicherheit
        self.assertEqual(set(kacheln), {"angebot", "bestand", "leergut", "crm", "rewe", "qs", "einkauf", "containerimport", "import", "verwaltung", "hr", "marketing", "controlling", "sicherheit"})
        self.assertTrue(set(rw.module["dashboard"]["pflichtmodule"]) <= set(kacheln))
        # Controlling, Leergut, Container-Import: nicht freigegeben; DNS besteht (25.10.2026) → 503-Platzhalter (GR-105)
        for neu, stand in (("controlling", "geplant"), ("leergut", "geplant"), ("containerimport", "geplant")):
            o = rw.modul(neu)["oberflaeche"][0]
            self.assertEqual((o["entwicklung"], o["freigabe"], o.get("dns", True)), (stand, "keine", True), neu)
        # HR: vom Inhaber am 23.10.2026 freigegeben (DNS, Keycloak-Client, Caddy, produktiv) – eigener Host mit DNS
        o = rw.modul("hr")["oberflaeche"][0]
        self.assertEqual((o["entwicklung"], o["freigabe"], o.get("dns", True), o["adresse"]),
                         ("fertig", "produktiv", True, "https://hr.dashboard-stafl.de/module/hr/"))
        # CRM: vom Inhaber am 23.10.2026 freigegeben (Keycloak-Client, Caddy, produktiv) – eigener Host mit DNS
        o = rw.modul("crm")["oberflaeche"][0]
        self.assertEqual((o["entwicklung"], o["freigabe"], o.get("dns", True), o["adresse"]),
                         ("fertig", "produktiv", True, "https://crm.dashboard-stafl.de/module/crm/"))
        # Marketing: vom Inhaber am 25.10.2026 freigegeben (DNS, Keycloak-Client, Caddy, produktiv) – eigener Host mit DNS
        o = rw.modul("marketing")["oberflaeche"][0]
        self.assertEqual((o["entwicklung"], o["freigabe"], o.get("dns", True), o["adresse"]),
                         ("fertig", "produktiv", True, "https://marketing.dashboard-stafl.de/module/marketing/"))
        # Sicherheit: vom Inhaber am 26.10.2026 freigegeben (DNS, Keycloak-Client, Caddy, produktiv); nie sperrbar, Kachel direkt nach der
        # Verwaltung im Bereich „Verwaltung & Daten“, Modulzugang ohne Standardrollen (zugang_rollen = [])
        m = rw.modul("sicherheit"); o = m["oberflaeche"][0]
        self.assertEqual((o["entwicklung"], o["freigabe"], o.get("dns", True), o["adresse"], o["sperrbar"]),
                         ("fertig", "produktiv", True, "https://sicherheit.dashboard-stafl.de/module/sicherheit/", False))
        self.assertEqual((m["dashboard_gruppe"], m["zugang_rollen"], m["reihenfolge"]), ("verwaltung", [], rw.modul("verwaltung")["reihenfolge"] + 1))
        self.assertEqual(rw.modul("import")["teil_von"], "verwaltung")
        self.assertEqual(rw.modul("import")["kachel_ziel"], "verwaltung.import")
        self.assertEqual(rw.modul("angebot")["kachel_ziel"], "eingabe")

    def test_unfertige_module_nicht_freigegeben(self):
        rw = regeln.laden(WURZEL)
        for mid in ("bestand", "crm", "rewe", "qs", "einkauf", "verwaltung"):
            for o in rw.modul(mid).get("oberflaeche", []):
                # Roadmap 10a: Verwaltung unter eigener Adresse; Phase 1 Bestand/Import: bestand.dashboard-stafl.de und Importzentrale
                if (mid, o["id"]) in (("verwaltung", "verwaltung"), ("verwaltung", "import"), ("bestand", "intern"), ("crm", "intern")):
                    self.assertEqual((o["entwicklung"], o["freigabe"]), ("fertig", "produktiv"))
                    continue
                self.assertEqual(o["freigabe"], "keine", f"{mid}.{o['id']}")
        # Inbetriebnahme Schritt 6: Dashboard und zentrale Anmeldung freigegeben (nur mit fertigem Entwicklungsstand)
        for mid, oid in (("dashboard", "start"), ("plattform", "anmeldung")):
            o = {x["id"]: x for x in rw.modul(mid)["oberflaeche"]}[oid]
            self.assertEqual((o["entwicklung"], o["freigabe"]), ("fertig", "produktiv"), f"{mid}.{oid}")

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
        self.assertEqual(anm["freigabe"], "produktiv")
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

    def test_zugang_rollen(self):
        # Standardrollen mit Modulzugang je Modul (z. B. Sicherheit: keine) – nur Standardrollen, nur Dashboard-Module
        self.p.ersetzen("regeln/module.toml", "reihenfolge = 10\ndashboard = true", "reihenfolge = 10\ndashboard = true\nzugang_rollen = []")
        self.assertEqual(self.p.fehler(), [])
        self.p.ersetzen("regeln/module.toml", "zugang_rollen = []", 'zugang_rollen = ["admin"]')
        self.assertFehler("zugang_rollen muss eine Liste aus viewer, editor sein")

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

    def test_aktion_im_code_nicht_registriert(self):
        self.p.ersetzen("app/api/aktionen/demo.php", "    case 'save_draft'", "    case 'geheim_export': respond([]);\n    case 'save_draft'")
        self.assertFehler("Aktion geheim_export wird im Code bearbeitet, ist aber in keinem regeln/aktionen/*.toml registriert")

    def test_registrierte_aktion_ohne_code(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", "[aktion.save_draft]", "[aktion.alt]\noberflaeche = \"angebot.eingabe\"\n\n[aktion.save_draft]")
        self.p.erzeugen()
        self.assertFehler("Aktion alt ist registriert")

    def test_aktion_doppelt_registriert(self):
        self.p.schreiben("regeln/aktionen/lager.toml", 'schema = 1\nmodul = "lager"\n\n[aktion.offer]\noberflaeche = "angebot.kunden"\noeffentlich = true\n')
        self.p.ersetzen("regeln/module.toml", 'pfade = ["app/api/lib/bestand.php"]', 'pfade = ["app/api/lib/bestand.php", "regeln/aktionen/lager.toml"]')
        self.p.erzeugen()
        self.assertFehler("jede Aktion gehört genau einem Modul")

    def test_mitarbeiteraktion_auf_externer_oberflaeche(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", 'oberflaeche = "angebot.eingabe"', 'oberflaeche = "angebot.kunden"')
        self.p.erzeugen()
        self.assertFehler("Mitarbeiter-Aktion auf externer Oberfläche angebot.kunden")

    def test_oeffentliche_aktion_auf_interner_oberflaeche(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", 'oberflaeche = "angebot.kunden"', 'oberflaeche = "angebot.eingabe"')
        self.p.erzeugen()
        self.assertFehler("öffentliche Aktion auf interner Oberfläche angebot.eingabe")

    def test_unbekannte_oberflaeche(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", 'oberflaeche = "angebot.eingabe"', 'oberflaeche = "angebot.backoffice"')
        self.p.erzeugen()
        self.assertFehler("oberflaeche „angebot.backoffice“ gibt es nicht")

    def test_kunden_wartung_nur_oeffentlich(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", "schreibend = true", "schreibend = true\nkunden_wartung = true")
        self.p.erzeugen()
        self.assertFehler("kunden_wartung nur für öffentliche Kundenaktionen")

    def test_wartung_frei_nicht_fuer_oeffentliche(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", "kunden_wartung = true", "kunden_wartung = true\nwartung_frei = true")
        self.p.erzeugen()
        self.assertFehler("wartung_frei nur für Mitarbeiter-Aktionen")

    def test_wartung_frei_nicht_fuer_beliebige_schreibaktionen(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", "schreibend = true", "schreibend = true\nwartung_frei = true")
        self.p.erzeugen()
        self.assertFehler("schreibende Aktion als wartung_frei")

    def test_fremde_herkunft_nur_fuer_festgelegte_oeffentliche(self):
        # Mitarbeiter-Aktion darf nie von fremden Seiten kommen (GR-109)
        self.p.ersetzen("regeln/aktionen/angebot.toml", "schreibend = true", "schreibend = true\nfremde_herkunft = true")
        self.p.erzeugen()
        self.assertFehler("fremde_herkunft nur für die festgelegten")

    def test_fremde_herkunft_nicht_fuer_beliebige_oeffentliche(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", "kunden_wartung = true", "kunden_wartung = true\nfremde_herkunft = true")
        self.p.erzeugen()
        self.assertFehler("fremde_herkunft nur für die festgelegten")

    def test_fremde_herkunft_kein_wahrheitswert(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", "kunden_wartung = true", 'kunden_wartung = true\nfremde_herkunft = "ja"')
        self.p.erzeugen()
        self.assertFehler("fremde_herkunft muss true oder false sein")

    def test_echtes_register_nur_abmelden1_von_fremd(self):
        rw = regeln.laden(WURZEL)
        fremd = sorted(n for n, a in regeln.aktionen_tabelle(rw).items() if a["fremde_herkunft"])
        self.assertEqual(fremd, ["abmelden1"])

    def test_lokale_anmeldung_kein_wahrheitswert(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", "schreibend = true", 'schreibend = true\nlokale_anmeldung = "ja"')
        self.p.erzeugen()
        self.assertFehler("lokale_anmeldung muss true oder false sein")

    def test_echtes_register_lokale_anmeldung(self):
        # Eigene Anmeldeverfahren, die auf Keycloak-Hosts gesperrt sind (GR-110) – Änderung nur bewusst
        rw = regeln.laden(WURZEL)
        lokal = {n for n, a in regeln.aktionen_tabelle(rw).items() if a["lokale_anmeldung"]}
        self.assertEqual(lokal, {"reauth", "setup", "login", "login_2fa", "twofa_begin", "twofa_enable", "twofa_disable",
                                 "change_password", "passkey_begin", "passkey_register", "passkey_rename", "passkey_delete",
                                 "passkey_login_begin", "passkey_login", "kunde_login", "kunde_passwort", "kunde_token_set",
                                 "kunde_token_check"})

    def test_falscher_wert_schreibend(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", "schreibend = true", 'schreibend = "ja"')
        self.p.erzeugen()
        self.assertFehler('schreibend muss true, false oder "post" sein')

    def test_erzeugte_liste_veraltet(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", "schreibend = true", "schreibend = false")
        self.assertFehler("aktionen-liste.php passt nicht zu regeln/aktionen/")

    def test_modul_passt_nicht_zum_dateinamen(self):
        self.p.ersetzen("regeln/aktionen/angebot.toml", 'modul = "angebot"', 'modul = "lager"')
        self.p.erzeugen()
        self.assertFehler("modul muss „angebot“ lauten")

    def test_veraltete_module_liste(self):
        self.p.erzeugen_module()
        self.assertEqual(self.p.fehler(), [])
        self.p.ersetzen("regeln/module.toml", 'name = "Lager"\nbeschreibung', 'name = "Lager neu"\nbeschreibung')
        self.assertFehler("module-liste.php passt nicht zu regeln/module.toml")

    def test_erzeugte_liste_ist_php(self):
        text = (self.p.wurzel / regeln.AKTIONEN_LISTE).read_text(encoding="utf-8")
        self.assertIn("'offer' => ['modul' => 'angebot', 'oberflaeche' => 'angebot.kunden', 'schreibend' => false, 'oeffentlich' => true, 'kunden_wartung' => true, 'wartung_frei' => false, 'fremde_herkunft' => false, 'lokale_anmeldung' => false],", text)
        self.assertIn("'save_draft' => ['modul' => 'angebot', 'oberflaeche' => 'angebot.eingabe', 'schreibend' => true,", text)

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
