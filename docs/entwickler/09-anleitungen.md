# 9 · Anleitungen

Schritt für Schritt für die häufigsten Aufgaben. Jede Anleitung endet mit denselben Pflichtschritten:

> **Abschluss jeder Änderung:** `python3 werkzeuge/regeln.py erzeugen` (wenn `regeln/` geändert) ·
> `python3 werkzeuge/doku.py erzeugen` · `python3 werkzeuge/regeln.py pruefen && python3 werkzeuge/doku.py pruefen` ·
> betroffene Testgruppen in beiden Speicherarten (`python3 werkzeuge/regeln.py betroffen --basis origin/main`) ·
> Kapitel dieser Dokumentation anpassen · Pull Request nach Vorlage.

Bereiche, die in [`regeln/module.toml`](../../regeln/module.toml) unter `[[koordination]]` stehen (Anmeldung, Rechte,
Speicherschicht, API-Einstieg, Regelwerk, Betrieb, globale Tests), ändert man nur in einem eigenen Pull Request mit
Abschnitt „Koordination“.

---

## Eine neue API-Aktion

1. **Register:** Eintrag in `regeln/aktionen/<modul>.toml` (Datei des Moduls, dem die Aktion fachlich gehört):

   ```toml
   [aktion.lager_buchen]
   oberflaeche = "bestand.intern"   # Host, auf dem die Aktion angeboten wird (GR-109)
   schreibend = true                # nur POST mit JSON; false = lesend, "post" = GET liest, POST schreibt
   ```

   Weitere Felder (`oeffentlich`, `kunden_wartung`, `wartung_frei`, `fremde_herkunft`, `lokale_anmeldung`) nur mit
   gutem Grund – Bedeutung in [`regeln/aktionen/LIESMICH.md`](../../regeln/aktionen/LIESMICH.md). Danach
   `python3 werkzeuge/regeln.py erzeugen` (schreibt `app/api/lib/aktionen-liste.php` – nie von Hand ändern).
2. **Code:** ein `case` in der Aktionsdatei des Moduls (`app/api/aktionen/<modul>.php`; Fachlogik in
   `app/api/module/<modul>/`). Muster:

   ```php
   case 'lager_buchen': {
       $me = require_perm('bestand.buchen', true);          // Anmeldung + Recht + CSRF (true = schreibend)
       $b = body();                                          // JSON, max. 6 MB
       $menge = $b['menge'] ?? null;
       if (!is_int($menge) || $menge <= 0) throw new InvalidArgumentException('Ungültige Menge.');   // → 422
       $neu = with_lock('bestand', function () use ($menge) {   // Sperre + Transaktion (SQLite)
           $d = store_read('bestand') ?? [];
           // … ändern, nur erweitern (GR-006) …
           store_write('bestand', $d);
           return $d;
       });
       audit('stock', 'Lager gebucht', [ /* Änderungen ohne personenbezogene Inhalte */ ]);
       respond(['ok' => true]);
   }
   ```

   Lesende Aktionen: `require_perm('…')` ohne `true`. Nur Administratoren: `require_auth(…, 'admin')` bzw. mit
   Bestätigung `require_admin_confirmation('<aktion>')`. Sensible Aktion mit Recht: `require_perm_confirmed('<recht>',
   '<aktion>')` und Eintrag im Katalog `BESTAETIGUNG` in `app/api/lib/sicherheit.php`.
3. **Neue Aktionsdatei?** Nur für ein neues Modul: `require __DIR__ . '/aktionen/<modul>.php';` am Ende der Liste in
   `app/api/index.php` (koordinationspflichtig) und Pfad in `regeln/module.toml` beim Modul eintragen.
4. **Oberfläche:** Aufruf über die `api()`-Hilfsfunktion der Seite (CSRF wird mitgeschickt); Knöpfe nur zeigen, wenn
   `may('<recht>')` – das ist Anzeige, die Sicherheit liefert Schritt 2 ([06 Oberflächen](06-oberflaechen.md)).
5. **Tests:** Rechte (ohne Anmeldung 401, ohne Recht 403, ohne CSRF 403), Fehlerfälle (422), Erfolg, Protokoll;
   bei `schreibend` auch, dass GET abgewiesen wird. Die Gruppe `aktionsregister` prüft das Register allgemein.

## Ein neues Recht

1. Eintrag in `PERMS` in `app/api/lib/rechte.php`:

   ```php
   'bestand.buchen' => ['g' => 'Bestand', 'l' => 'Lagerbuchungen erfassen', 'k' => 'machen', 'd' => [], 'r' => ['bestand.sehen']],
   ```

   `g` Gruppe (Anzeige), `l` Bezeichnung, `k` `sehen`|`machen`, `d` Standardrollen (`viewer`, `editor`; meist leer –
   neue Rechte gibt der Administrator in „Rollen und Rechte“), `r` Voraussetzungen (bearbeiten setzt sehen voraus).
2. Name immer `<modul>.<recht>` (GR-103) – dann ist keine Zuordnung nötig. Abweichende Namen nur mit Eintrag in
   `regeln/berechtigungen.toml` (`[zuordnung]`). **Bestehende Rechte nie umbenennen** (gespeicherte Rollenrechte).
3. Wichtig: Ein neues Recht mit Standardrollen in `d` bekommen auch Standardrollen, deren Rechte bereits gespeichert
   sind (`rechte.bekannt` in `rights_roles()`); mit leerem `d` bekommt es zunächst niemand außer Administratoren.
4. Server: `require_perm('<recht>')` in jeder Aktion, die es braucht. Oberfläche: `may('<recht>')`.
5. Die Verwaltung („Rollen und Rechte“) zeigt das Recht automatisch unter seinem Modul. Tests: Rechte-Gruppe des
   Moduls plus `rechte`/`rollen`, falls Standards betroffen sind. Referenz: [Rechte](referenz/rechte.md).

## Ein neues Speicher-Dokument

1. Eintrag in `regeln/datenverantwortung.toml`: `name`, `eigentuemer` (Modul), `schutz`
   (`oeffentlich`|`intern`|`vertraulich`|`geheim`), `beschreibung`, ggf. `leser`/`schreiber`, `historie`.
2. Zugriff nur über `store_read`/`store_write`/`with_lock` (Name als Zeichenkette im Aufruf, damit die Prüfung ihn
   sieht; berechnete Namen: `dynamisch = true`).
3. Format von Anfang an erweiterbar anlegen (Objekt mit Feldern, optionale Felder mit Standardwerten beim Lesen).
   Ein späteres Feld fügt man hinzu, ohne alte Daten umzuschreiben (GR-006); entfernen/umdeuten braucht eine Migration
   mit Freigabe des Inhabers. [05 Daten](05-daten.md).
4. Fremde Dokumente nie direkt lesen/schreiben, sondern über Funktionen des Eigentümers (GR-101); neue Querzugriffe
   sind koordinationspflichtig.

## Ein Feld zu bestehenden Daten hinzufügen

1. Beim Lesen einen Standardwert annehmen, wenn das Feld fehlt (`$u['feld'] ?? …`).
2. Beim Schreiben das Feld nur setzen, wenn es einen Wert hat; ältere Oberflächen, die das Feld nicht mitschicken,
   dürfen es nicht löschen (Muster: `array_key_exists('feld', $b)` – fehlt es, bleibt der alte Wert).
3. Die Vorversion muss mit dem neuen Feld weiterlaufen (Rückfall): sie ignoriert unbekannte Felder – darf aber nicht
   mehr Rechte o. Ä. daraus ableiten. Im Pull Request den Rückfallweg nennen.

## Ein neues Modul (mit Kachel)

1. **Register:** `[[modul]]` in `regeln/module.toml` mit `id`, `name`, `beschreibung`, `icon`, `reihenfolge`,
   `dashboard = true`, `agent`, `abhaengigkeiten`, `testgruppen`, `pfade` (bzw. `pfade_geplant`), `hinweise` und
   `[[modul.oberflaeche]]` (`id`, `name`, `art` intern/extern, `adresse`, `entwicklung` = `geplant`, `freigabe` =
   `keine`, `sperrbar`). `python3 werkzeuge/regeln.py erzeugen`.
2. Damit entstehen automatisch die Kachel (Stand „geplant“) und das Recht `<modul>.zugang` (Standard: beide
   Standardrollen). Die Adresse des Moduls muss im `Caddyfile` als 503-Platzhalter stehen, bis es freigegeben ist
   (GR-105; die CI prüft das).
3. **Code:** Server unter `app/api/module/<modul>/` + `app/api/aktionen/<modul>.php` + `regeln/aktionen/<modul>.toml`;
   Seite unter `app/module/<modul>/` nach dem Muster von HR/CRM (Kopf mit `.stafl-zurueck`, `theme.js`,
   `STAFL_THEME.konto(...)` nach dem Status, eigene `api()`); Rechte `<modul>.*`; eigene Dokumente; Tests.
4. **Entwicklungsstand** im Register hochsetzen (`in_entwicklung` → `in_pruefung` → `fertig`). Testen lässt sich ein
   nicht freigegebenes Modul über die Modulverwaltung (Testfreigabe mit eingetragenen Testern).
5. **Produktiv** wird ein Modul nur mit Freigabe des Inhabers: Keycloak-Client, Apache-Host
   (`deploy/anmeldung/apache-oidc.conf`, `WA_OBERFLAECHE`), Caddy-Route, ggf. DNS – Ablauf wie in den
   Inbetriebnahme-Dokumenten der bisherigen Module ([08 Betrieb](08-betrieb.md)).

## Eine neue Ansicht im Eingabebereich

Kurzfassung (ausführlich in [06 Oberflächen](06-oberflaechen.md)): Reiter `#vt-<name>` und Container
`#view-<name>` in `app/admin/index.html` · Name in `VIEWS` (und ggf. `ADMIN_VIEWS`), Recht in `VIEW_PERM`,
Bereichs-Host in `BEREICH_VIEWS` (`app/assets/admin.js`) · Darstellung in einem Teilskript, das
`W.views.<name> = render` setzt · Aufruf in `setView` · Test mit Bildschirmfoto bei 1440 und 390 px.

## Eine neue Testgruppe

1. Datei `tests/e2e/test_<gruppe>.py` mit Kopfkommentar (Docstring), `check()`-Funktion und Abschlusszeile
   `print(f'{sum(res)}/{len(res)} passed')` ([07 Tests](07-tests.md)).
2. Eintrag in `SUITES` in `tests/run_e2e.py` (Port-Platzhalter, Testdaten, Administrator, Umgebungsvariablen) und
   Laufzeitgewicht in `GEWICHT` (sonst schlägt `tests/unit/test_run_e2e_teile.py` fehl).
3. Gruppe beim Modul in `regeln/module.toml` unter `testgruppen` und in `tests/README.md` eintragen.

## Eine sensible Aktion mit Passwortbestätigung

1. Eintrag in `BESTAETIGUNG` (`app/api/lib/sicherheit.php`): `'<aktion>' => ['<Gruppe>', '<Beschreibung>', <fest>]`
   (`true` = nicht abschaltbar).
2. In der Aktion `require_admin_confirmation('<aktion>')` bzw. `require_perm_confirmed('<recht>', '<aktion>')`.
   Auf Keycloak-Hosts bestätigt der Mitarbeiter durch erneute Anmeldung bei Keycloak statt mit einem Passwort
   ([04 Anmeldung und Rechte](04-anmeldung-rechte.md)). Die Gruppe `bestaetigung` prüft, dass jede Stelle ihren
   Katalogschlüssel nutzt.

## Eine neue Umgebungsvariable

1. Lesen mit `getenv()` bzw. `oidc_einstellung()` und sicherem Standardwert (fehlt sie, verhält sich die Anwendung
   wie bisher).
2. Auf dem Server setzt man sie in `.env` bzw. `docker-compose*.yml` – das ist eine Serveränderung mit Freigabe;
   Muster in `.env.example`. Dokumentieren in [03 Server](03-server.md) (Tabelle der Umgebungsvariablen).
3. In Tests über den vierten Eintrag in `SUITES` setzen.

## Datenformat inkompatibel ändern (Ausnahme)

Nur mit Freigabe des Inhabers: Migration als eigenes Skript (Muster `deploy/datenbank.py`), Sicherung vorher, Weg
zurück beschreiben, eigener Pull Request. Vorher prüfen, ob ein zusätzliches Feld reicht (fast immer).

Stand: 2026-10-24
