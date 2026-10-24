# 5 · Daten und Speicher-Dokumente

Dieses Kapitel erklärt, wo die Daten liegen, wie die wichtigsten Dokumente aufgebaut sind und welche Regeln beim Ändern
eines Datenformats gelten. Die Funktionen der Speicherschicht beschreibt [Kapitel 3.5](03-server.md#35-speicherschicht-appapistoragephp);
die vollständige Liste aller Dokumente mit Eigentümer, Schutzstufe, Lesern und Schreibern steht in
[referenz/daten.md](referenz/daten.md) (erzeugt aus `regeln/datenverantwortung.toml`).

Alle Beispiele unten verwenden erfundene Testwerte. Echte Daten gehören nie ins Repository (GR-007); Testdaten nur aus
`tests/fixtures/`.

## 5.1 Speicherarten

Der Server kennt nur **Dokumente**: einen Namen und einen JSON-Wert. Wo sie liegen, entscheidet `store_mode()` einmal je
Anfrage:

| Speicherart | Erkennung | Ablage |
| --- | --- | --- |
| Dateien (Standard) | keine Datei `.sqlite-active` | je Dokument `daten/<name>.php` (im Container `/var/www/html/data`), Inhalt: Sperrzeile `<?php http_response_code(404); exit; ?>` + JSON; Unterordner für Namen mit `/` (z. B. `daten/protokoll/2026-01.php`) |
| SQLite | `daten/.sqlite-active` vorhanden | `daten/.sqlite/store.sqlite`, Tabelle `documents(name, payload, mtime)`, Schema `user_version = 1` |

Auch bei SQLite bleiben drei **Seitendateien** Dateien (`STORE_SIDECARS`): `mail-schluessel` (Schlüssel des
Postfach-Passworts), `sicherung` und `deployment` (Statusdateien der Skripte). Außerhalb der Speicherschicht liegen die
Länder- und Ortsdatenbank (`geo/`).

Die SQLite-Ablage übernimmt die Dokumente **unverändert** als JSON – es gibt keine Tabellen je Kunde oder Artikel. Für den
Code ist die Speicherart daher unsichtbar; jede Änderung muss in beiden Arten funktionieren (die E2E-Suite läuft in
beiden, lokal mit `WA_TEST_STORAGE=sqlite`).

**Umschalten** (nur Betreiber, im Wartungsfenster, mit Freigabe): `sh deploy/datenbank-umschalten.sh migrate` bzw.
`rollback`; prüfen mit `python3 deploy/datenbank.py check daten`. Ablauf, Grenzen und Rückfall:
[datenbank.md](../datenbank.md). Nie nur den Marker löschen oder alte Dateien über die Datenbank kopieren.

**Sicherung** (`deploy/sichern.sh`): täglich über einen eigenen systemd-Timer (`deploy/sicherung-einrichten.sh`; ohne
Timer ruft `aktualisieren.sh` sie höchstens einmal am Tag auf; sofort: `--jetzt`), die letzten 30 Stände unter
`sicherungen/` im Projektordner, nur für root lesbar. Jede Sicherung wird probeweise entpackt und geprüft; bei SQLite
über die Backup-API (konsistenter Schnappschuss). Nicht gesichert wird `mail-schluessel` – nach einer Wiederherstellung
auf neuem Server das Postfach-Passwort neu eingeben. Läuft Keycloak, wird dessen Datenbank zusätzlich gesichert. Status
im Dokument `sicherung` (Anzeige unter „Sicherheit“).

## 5.2 Formate nur erweitern (GR-006)

> Code muss bestehende Daten weiter lesen können, damit ein Rückfall auf die Vorversion keine Daten beschädigt.
> Unverträgliche Änderungen brauchen eine eigene Migration mit Freigabe. (`regeln/katalog.toml`, GR-006)

Ein Release kann jederzeit auf die Vorversion zurückfallen (automatisch, wenn der Healthcheck scheitert). Dann liest
**alter Code neue Daten** und **neuer Code alte Daten**. Daraus folgen die Muster, die der Code durchgehend verwendet:

**1. Neue Felder sind optional und fehlen, solange sie leer sind.** `user_save` schreibt `vorname`, `nachname`,
`email`, `rollen`, `grant`, `deny`, `twofaPflicht` nur, wenn sie einen Wert haben; `clean_model` schreibt `nameRaw`,
`cell`, `variants`, `sale` nur bei Bedarf; `clean_master` ebenso `vkGruppe` und `gtin`:

```php
if ($vk !== '') $e['vkGruppe'] = $vk;
if ($gtin !== '') $e['gtin'] = $gtin;
```

**2. Lesen mit Standardwert.** Fehlt ein Feld, gilt das bisherige Verhalten:

```php
// lib/nutzer.php – Mitarbeiter ohne Anmeldung; fehlt das Feld, hat der Mitarbeiter einen Zugang (ältere Daten)
function nutzer_hat_zugang(array $u): bool { return ($u['zugang'] ?? true) !== false; }
// lib/sicherheit.php – gespeicherte Einstellungen über die Standardwerte legen
if ($SEC === null) $SEC = array_merge(SEC_DEFAULTS, store_read('sicherheit') ?? []);
// lib/angebote.php – Wochenangebot öffentlich, solange nichts anderes gespeichert ist
function std_public(): bool { $d = offers_load(); return !array_key_exists('stdPublic', $d) || !empty($d['stdPublic']); }
```

Weitere Fälle: `mailAngebot` beim Kunden (fehlt = Wochenangebot per E-Mail an), `copy` in `order_settings()`,
`fw()` mit `FW_DEFAULTS`, `hr_person_norm` (Arbeitstage Mo–Fr, `aktiv` an), `crm_blatt` mit `crm_standard`.

**3. Fehlt ein Feld in der Anfrage, bleibt der gespeicherte Wert.** Eine ältere Oberfläche (Browser mit altem Skript
nach einem Release) darf keine neuen Felder löschen:

```php
// lib/sicherheit.php, sec_clean
'pwLeak' => array_key_exists('pwLeak', $b) ? !empty($b['pwLeak']) : !empty($old['pwLeak']),   // ältere Oberfläche ohne Feld: unverändert
```

Ebenso `bestaetigungAus` (Sicherheit), `twofaPflicht` und `grant`/`deny` (`user_save`), `gruppen` (`offers_save`).

**4. Alte Fassung bekommt nie mehr Rechte.** Mehrere Rollen je Mitarbeiter stehen in `role` (Hauptrolle, kennt jede
Fassung) plus optional `rollen`. Als Hauptrolle wählt `user_save` bevorzugt eine Standardrolle:

```php
// Hauptrolle bevorzugt eine Standardrolle: ältere Fassungen (Rückfall) kennen nur diese – nie mehr Rechte als hier
$std = array_values(array_intersect($liste, PERM_ROLES));
$role = $std[0] ?? $liste[0];
```

Das Dokument `rechte` merkt sich in `bekannt` den Rechtekatalog beim Speichern; später hinzugekommene Rechte erhalten die
Standardrollen mit ihrem Standardwert (`rights_roles`), Dokumente ohne `bekannt` gelten als Stand `PERMS`.

**5. Unbekannte Felder erhalten.** `hr_person_norm` hängt nicht erkannte Felder wieder an
(`+ array_diff_key($p, …)`), `crm_kunde_save` schreibt `array_merge($alt, $neu, …)`. So überlebt ein Feld einer neueren
Fassung das Speichern durch eine ältere.

> **Achtung, Gegenbeispiel:** `kunde_save` (`aktionen/kundenverwaltung.php`) baut den Kundensatz neu aus
> `CUSTOMER_FIELDS` und übernimmt vom alten Satz nur `weekly`, `mailLast`, `abgemeldet` (dazu `created`, `login`).
> Ein neues Feld am Kunden muss dort ausdrücklich übernommen werden, sonst verwirft es das nächste Speichern. Felder aus
> `CUSTOMER_FIELDS`, die die Anfrage nicht enthält, werden leer gespeichert.

**6. Typen stabil halten.** JSON-Schlüssel wie `"24"` kommen in PHP als Zahl an; `clean_variants` wandelt sie
zurück (`$oid = (string)$oid`), sonst gingen Kundenpreise älterer Angebote mit Zahlen-ID verloren.

**7. Altformate beim Lesen übernehmen.** `users_load()` übernimmt das frühere Dokument `admin` (ein Passwort) einmalig
unter Sperre als Nutzer „admin“ ins Dokument `nutzer` und löscht `admin`.

Hell/Dunkel: optionales Feld `theme` (`'light'` | `'dark'`; fehlt = wie das Gerät) am Mitarbeiter, gesetzt über die
Aktion `theme_save` (nur der eigene Datensatz), ausgeliefert im Status (`user.theme`); jede Seite übernimmt es mit
`STAFL_THEME.konto` (`app/assets/theme.js`), der Browser merkt es sich zusätzlich unter `wochenangebot.theme`.

**Wann ist eine Migration nötig?** Wenn alter Code die neuen Daten nicht mehr richtig lesen kann: Feld umbenennen oder
Typ ändern, Bedeutung eines Werts ändern, Dokument aufteilen oder zusammenlegen, Pflichtfeld einführen. Dann gilt:

- eigener PR mit Abschnitt „Koordination“ (Speicherschicht ist koordinationspflichtig), Freigabe des Inhabers;
- Migrations- **und** Rückfallweg beschreiben und testen (Vorbild: `deploy/datenbank-umschalten.sh` mit `migrate` und
  `rollback`, Tests `tests/deploy/test_datenbank.py`);
- die Regel nennt als Tests die E2E-Gruppe `storage` und `tests/deploy/test_datenbank.py`.

Besser ist fast immer: neues optionales Feld ergänzen, altes weiter schreiben, bis kein unterstützter Stand es mehr braucht.

## 5.3 Dokumente im Einzelnen

Die Felder sind aus den Prüf- und Schreibfunktionen ermittelt; `?` = optional (fehlt, wenn leer).

### Plattformkern

**`nutzer`** (geheim, `lib/nutzer.php`): `{"users": [ … ]}`.

```json
{"users": [{
  "id": "u0123456789ab", "username": "max-muster", "name": "Max Muster", "vorname": "Max", "nachname": "Muster",
  "email": "max@example.invalid", "role": "editor", "rollen": ["r0a1b2c3d"], "active": true,
  "hash": "<password_hash>", "mustChange": false, "sv": 3,
  "created": "2026-01-05T08:00:00Z", "createdBy": "admin", "lastLogin": null, "changed": "2026-01-06T09:00:00Z",
  "grant": ["kunden.sehen"], "deny": ["bestand.einkaufspreise"], "twofaPflicht": true
}]}
```

| Feld | Bedeutung |
| --- | --- |
| `role` | Hauptrolle: `viewer`, `editor`, `admin` oder eigene Rolle `r<8 hex>` |
| `rollen?` | weitere Rollen (nie `admin`), Rechte addieren sich |
| `zugang?` | nur `false` = Mitarbeiter ohne Anmeldung (z. B. Lager, Urlaubsplanung); dann immer `active: false` |
| `sv` | Sitzungsversion; Erhöhen beendet alle Sitzungen (Passwort, zweiter Faktor, Passkeys) |
| `grant?`, `deny?` | Rechte-Ausnahmen je Nutzer; `deny` hat Vorrang |
| `totp?`, `totpLast?`, `recovery?` | Authenticator-App (Geheimnis, letzter Zeitschritt, Hashes der Wiederherstellungscodes) |
| `passkeys?`, `geraete?` | Passkeys (WebAuthn), vertraute Geräte (`{h, name, seit, zuletzt, f}`, höchstens 10) |
| `failCount?`, `failAt?`, `lockedUntil?`, `lockTries?` | Fehlversuche und Sperre |
| `confirmFailures?`, `confirmSeen?`, `confirmUntil?` | Bremse der Passwortbestätigung |
| `mailInfo?` | letzte E-Mail mit Zugangsdaten `{t, to, by, ok, mitPasswort}` |
| `oidcSub?` | Verknüpfung mit Keycloak (unveränderliche Kennung `sub`) |
| `mustChange`, `mustChangeGrund?` | Passwortwechsel erzwungen |

Nie in Antworten: `hash`, `totp`, `recovery`, Passkey-Schlüssel. Nach außen geht nur `user_public()`.

**`rechte`**: Rechte der Standardrollen.
`{"roles": {"viewer": ["preisverlauf.sehen", …], "editor": [ … ]}, "bekannt": [ …Katalog… ], "updatedAt": "…", "updatedBy": "…"}`.
Ohne Dokument gelten die Standardwerte des Rechtekatalogs (`d` in `PERMS`, Modulzugang für beide Standardrollen). Rechte im Einzelnen: [referenz/rechte.md](referenz/rechte.md).

**`rollen`**: eigene Rollen und Namen der Standardrollen.

```json
{"eigene": {"r0a1b2c3d": {"name": "Vertrieb", "beschreibung": "…", "rechte": ["kunden.sehen", "crm.sehen"],
                          "erstellt": "…", "von": "…", "geaendert": "…", "geaendertVon": "…"}},
 "namen": {"viewer": "Lager", "editor": "Büro"}}
```

**`sitzungen`** (geheim): Sitzungsregister der Mitarbeiter, Schlüssel = Register-ID (24 Hex-Zeichen, in
`$_SESSION['sid']`). `{"<sid>": {"uid": "u…", "ip": "…", "ua": "…", "created": "…", "seen": 1767600000}}`. Veraltete
Einträge (älter als `idleMinutes`) entfernt `sess_prune`. Eine Sitzung gilt nur, solange sie hier steht – so können
Administratoren Sitzungen beenden. Kunden haben ein eigenes Register `kundensitzungen`.

**`sicherheit`**: Sicherheitseinstellungen, gelesen über `sec()` mit `SEC_DEFAULTS`: `twofa` (`off`, `admins`,
`all`), `pwMin`, `pwComplex`, `pwLeak`, `idleMinutes`, `ipEnabled`, `adminIps`, `lockAfter`, `lockMinutes`,
`geoEnabled`, `geoMode` (`block`/`allow`), `geoCountries`, `geoScope` (`admin`/`all`), `bestaetigungAus`,
`bestaetigungMinuten`. Geschrieben nur über `sec_clean` (schützt u. a. vor Selbstaussperrung).

**`module`**: Laufzeitzustand je Oberfläche (`lib/module.php`):

```json
{"wartung":  {"hr.intern": {"active": true, "grund": "Umbau", "message": "…", "until": "2026-01-05T18:00",
                            "ab": null, "since": "…", "by": "…", "changed": "…"}},
 "freigabe": {"rewe.intern": {"wert": "test", "grund": "…", "von": "…", "t": "…"}},
 "tester":   {"rewe.intern": ["u0123456789ab"]},
 "verlauf":  [{"t": "…", "wer": "…", "bereich": "hr.intern", "alt": "normal", "neu": "wartung", "grund": "…", "ab": null, "bis": "…"}]}
```

`freigabe` gilt nur innerhalb von `MODUL_FREIGABE_ERLAUBT` aus dem Register, sonst der Registerwert; `verlauf` hält die
letzten 100 Änderungen. Die Wartung der Kundenseite (`angebot.kunden`) steht weiter im Dokument **`wartung`**:
`{"active": true, "message": "…", "until": "…", "since": "…", "by": "…", "changed": "…"}`.

**`protokoll/<JJJJ-MM>`**: Liste der Einträge eines Monats (UTC), nur anhängen; Aufbau in
[Kapitel 3.7](03-server.md#37-protokoll-audit). Änderungen `d` haben die Form
`{"k": "<Schlüssel>", "code": "…", "name": "…", "f": "<Feld>", "from": "…", "to": "…"}`.

Weitere Dokumente des Kerns (Firewall, Mailversand, Benachrichtigungen, Integrität …): [referenz/daten.md](referenz/daten.md).

### Angebot

**`entwurf`** und **`angebot`**: das Datenmodell aus `clean_model()` (`lib/angebote.php`). Der Entwurf trägt zusätzlich
`savedAt`, `savedBy`, `rev`; das veröffentlichte Angebot `publishedAt`. Jede Veröffentlichung legt das vorige Angebot
als `versionen/<JJJJMMTT-hhmmss>-<hex>` ab (höchstens `keep_versions`) und den Preisverlauf `historie/<id>`.

```json
{"meta": {"week": 2, "year": 2026, "notice": "", "title?": "…", "source?": "…", "sheetName?": "…"},
 "sections": ["Frischfleisch"],
 "groups": [{"id": "g1", "name": "Rind", "section": "Frischfleisch"}],
 "items": [{
   "id": "i1", "code": "1001", "name": "Testartikel Rinderhüfte", "category": "Rind", "origin": "DE",
   "condition": "frisch", "groupId": "g1",
   "price": {"status": "value", "value": 12.5}, "altPrices": [],
   "variants": {"kunde-a": {"status": "value", "value": 11.9}, "std": {"status": "hidden"}},
   "sale": {"value": 9.9, "offers": {"kunde-a": {"status": "none"}}, "since": "…"}
 }]}
```

| Feld | Werte |
| --- | --- |
| `category` | `CATEGORIES`: Rind, Kalb, Schwein, Lamm & Schaf, Geflügel, Knochen, Sonstiges (unbekannt → Sonstiges) |
| `condition` | `CONDITIONS`: frisch, gefroren, frisch-gefroren, dry-aged, unbekannt |
| `price`, `altPrices[]` | `{status: value|request|none, value?, raw?, label?}`, `value` 0 bis unter 100 000, 4 Nachkommastellen; höchstens 5 Zusatzpreise |
| `variants?` | Kundenpreise je Angebots-ID: `{status: value|request|hidden, value?, carried?}`; unter `std` nur `{status: hidden}` = im Wochenangebot ausgeblendet; Schlüssel gelöschter Angebote fallen weg |
| `sale?` | Sonderpreis „solange der Vorrat reicht“: Grundpreis `value`, je Angebot abweichend `{value}` oder `{status: none}` |
| `cell?`, `nameRaw?` | Zelladresse und Originaltext der Excel-Datei (intern) |

Grenzen: höchstens 5000 Artikel und 1000 Gruppen; IDs `^[A-Za-z0-9_-]+$`; Artikelnummer `^[0-9A-Za-z./-]+$`.
`variants`, `sale` und `cell` verlassen den Server nie roh – `offer_resolve()` löst sie je Angebot auf und entfernt sie
(GR-001, GR-002, GR-005).

**`angebote`**: Kundenangebote.
`{"rev": 4, "offers": [{"id": "kunde-a", "name": "Wochenangebot Kunde A", "fallback": "standard", "gruppen?": ["10"]}], "stdPublic": true, "updatedAt": "…", "updatedBy": "…"}`.
`fallback`: `standard` = ohne eigenen Preis Standardpreis zeigen, `hidden` = Artikel ausblenden. `gruppen`: Kundengruppen,
deren Kunden das Angebot ohne eigene Freischaltung sehen (je Gruppe höchstens ein Angebot). Fehlt das Dokument, gelten
`OFFER_DEFAULTS`. Neue IDs dürfen nicht mit `e-` beginnen (Einzelangebote) und nicht nur aus Ziffern bestehen.

Bestellwünsche (`bestellungen`) und Einzelangebote (`einzelangebote`): [bestell-api-v1.md](../bestell-api-v1.md),
[architektur.md](../architektur.md).

### Verwaltung

**`kunden`**: `{"rev": 7, "customers": [ … ], "updatedAt": "…"}`.

```json
{"id": "k0123456789ab", "nr": "10001", "gruppe": "10", "vertreter": "3", "vertreter2": "",
 "firma": "Testfirma GmbH", "ansprechpartner": "Erika Beispiel", "strasse": "Musterweg 1", "plz": "20000",
 "ort": "Hamburg", "land": "Deutschland", "email": "einkauf@example.invalid", "telefon": "", "notiz": "",
 "angebote": ["std", "kunde-a"], "active": true, "mailAngebot": true, "created": "…", "changed": "…",
 "login": {"username": "testfirma", "hash": "<password_hash>", "active": true, "mustChange": false, "sv": 1,
           "created": "…", "lastLogin": null, "failCount": 0, "lockedUntil": 0}}
```

Weitere Felder: `weekly` (zuletzt gesendetes Wochenangebot), `mailLast` (letzte E-Mail `{typ, t, ok, to}`),
`abgemeldet`; im Zugang `login` u. a. `pwSet`, `mustChangeGrund`, `geraete` und `token` (Einmal-Link
`{h: SHA-256, exp, p: Zweck, t}`, nie der Link selbst). `login: null` = kein Portalzugang. Freigeschaltete Angebote
berechnet `customer_offers()` aus `angebote` (direkt) und der Kundengruppe.

**`kundengruppen`**, **`vkgruppen`**, **`vertreter`**: je Liste `{"rev": 2, "groups": [{"nr": "10", "name": "…", …}], "updatedAt": "…", "updatedBy": "…"}`;
Felder je Liste in `GRUPPEN_LISTEN` (`lib/kunden.php`): Kunden- und VK-Gruppen `name`, `klasse`, `kategorie`;
Vertreter `name`, `kurz`, `telefon`, `plz`, `ort`, `land`. Nummer `^[0-9A-Za-z._-]{1,10}$`, höchstens 2000.

**`stammdaten`**: Artikelstammdaten aus `clean_master()`.
`{"rev": 12, "updatedAt": "…", "updatedBy": "…", "articles": [{"code": "1001", "name": "Testartikel Rinderhüfte", "category": "Rind", "origin": "DE", "condition": "frisch", "vkGruppe?": "200", "gtin?": "4000000000000"}]}`.
Höchstens 20 000 Sätze, Artikelnummern eindeutig über `code_key()` (führende Nullen und Groß-/Kleinschreibung zählen
nicht), GTIN 8–14 Ziffern.

### Bestand

**`bestand`** (vertraulich, nie öffentlich – GR-001, GR-008), geschrieben von `bestand_speichern()`:

```json
{"date": "2026-01-05", "source": "bestand-test.xlsx", "importedAt": "…", "importedBy": "…",
 "articles": [{"code": "1001", "name": "Testartikel", "kg": 120.5, "mhd": "2026-02-01", "mhdKg": 40.0,
               "lots": [{"lot": "P-1", "marke": "", "arrival": "2026-01-02", "mhd": "2026-02-01", "kolli": 4, "kg": 40.0, "ek": 8.25}]}],
 "incoming": [{"code": "1002", "name": "Testartikel 2", "lot": "", "marke": "", "arrival": "2026-01-09", "kg": 300.0}]}
```

`ek` (Einkaufspreis €/kg) geht nur an Nutzer mit `bestand.einkaufspreise` (`stock_ohne_ek`). Nur Artikel mit Bestand
über 0 kg werden gespeichert. Wochenpreise und Zugänge: [bestand-wochenpreise.md](../bestand-wochenpreise.md).

### HR (`module/hr/urlaub.php`)

Mitarbeiter sind die Nutzer der Plattform (`users_load()`); HR speichert nur eigene Angaben.

- **`hr-personal`**: `{"rev": 3, "personen": [{"id": "u0123456789ab", "nutzer": "u0123456789ab", "vorname": "…", "nachname": "…", "abteilung": "Lager", "pos": 10, "arbeitstage": [1,2,3,4,5], "aktiv": true, "jahre": {"2026": {"anspruch": 30, "uebertrag": 2.5}}, "personalnummer": "", "geaendert": "…"}]}`.
  Ohne gespeicherte Angaben gelten Standardwerte; Einträge ohne Mitarbeiter bleiben als Altbestand lesbar.
- **`hr-abwesenheiten`**: `{"rev": 9, "eintraege": [{"id": "a0123456789ab", "person": "u…", "art": "U", "von": "2026-03-02", "bis": "2026-03-06", "status": "beantragt", "notiz": "", "vertretung": null, "quelle": "antrag", "erfasst": {"t": "…", "by": "…", "byId": "u…"}}]}`.
  `art`: `U` Urlaub, `K` Krank, `G` Gleittag, `X` freier Tag. `status`: `beantragt`, `genehmigt`, `abgelehnt`,
  `zurueckgezogen`, `storniert` – Einträge werden nie gelöscht, nur der Status ändert sich (mit
  `entscheidung: {t, by, grund}`). `quelle`: `antrag`, `personalstelle`, `zeiterfassung`; optional `geaendert`,
  `urlaubAbzug` (Krankheit vom Urlaub abgezogen). Überschneidungen (`hr_kollision`) gelten nur zwischen aktiven
  Einträgen derselben Gruppe: Abwesenheiten (U/K/G) untereinander und freie Tage (X) untereinander – ein freier Tag in
  einer Urlaubswoche zählt dort nur nicht mit.
- **`hr-einstellungen`**: `{"rev": 1, "sperren": [{"von": "…", "bis": "…", "text": "Inventur"}], "ferien": [ … ]}`.

### CRM (`module/crm/crm.php`)

Kundenstammdaten liest das CRM nur über Funktionen der Verwaltung; eigene Dokumente (alle unter der Sperre `crm-kunden`):

- **`crm-kunden`**: `{"rev": 5, "updatedAt": "…", "eintraege": {"k0123456789ab": {"segment": "Gastronomie", "phase": "Angebot", "kontakte": [{"name": "…", "funktion": "…", "telefon": "…", "email": "…"}], "anrufStatus": "Offen", "wiedervorlage": "2026-01-12", "geaendert": "…", "geaendertVon": "…"}}}`.
  Schlüssel = Kunden-ID der Verwaltung oder Interessenten-ID (`i…`). `crm_kunde_save` ändert nur die mitgeschickten
  Felder (`array_merge` mit dem gespeicherten Blatt); fehlende liefert beim Lesen `crm_standard()`. Alle Felder mit Prüfung: `crm_felder()`.
- **`crm-interessenten`**: `{"rev": 2, "updatedAt": "…", "liste": [{"id": "i0123456789ab", "firma": "…", "ansprechpartner": "…", "strasse": "…", "plz": "…", "ort": "…", "land": "…", "telefon": "…", "email": "…", "vertreter": "", "vertreter2": "", "aktiv": true, "erstellt": "…", "erstelltVon": "…", "geaendert": "…", "geaendertVon": "…"}]}`.
- **`crm-aktivitaeten`**: `{"rev": 40, "updatedAt": "…", "liste": [{"id": "a…", "key": "k…", "art": "Telefonat", "notiz": "…", "naechster": "…", "faellig": "…", "at": "…", "von": "…", "vonId": "u…", "firma": "Testfirma GmbH", "nr": "10001"}]}`.
  `firma` und `nr` sind Schnappschüsse (GR-106); höchstens 50 000 Einträge, die ältesten fallen weg.

## 5.4 Datenverantwortung (GR-101)

Jedes Dokument hat **genau einen Eigentümer** (ein Modul). Eingetragen in `regeln/datenverantwortung.toml`:

```toml
[[dokument]]
name = "stammdaten"
eigentuemer = "verwaltung"
leser = ["angebot", "bestand"]   # master_save (aktionen/bestand.php) speichert über stammdaten_speichern() der Verwaltung
schutz = "intern"
beschreibung = "Artikelstammdaten (Bezeichnung, Fleischart, Herkunft, Zustand, VK-Gruppe, GTIN)"
```

| Feld | Bedeutung |
| --- | --- |
| `eigentuemer` | Modul, das das Dokument schreibt und sein Format verantwortet |
| `leser` | Module, die es lesen dürfen (der Plattformkern darf für Betrieb, Sicherung, Diagnose alles lesen) |
| `schreiber` | Module, die es zusätzlich schreiben dürfen – nur über Funktionen des Eigentümers; Vermerk „Altbestand“ = heutige Querzugriffe, die beim Umzug in Module ersetzt werden |
| `schutz` | `oeffentlich` (gefiltert an Besucher), `intern` (Mitarbeiter), `vertraulich` (Preise, Kontaktdaten; nur mit Recht), `geheim` (Hashes, Schlüssel, Sitzungen; nie in Antworten oder Protokollen) |
| `historie` | wie frühere Stände gegen spätere Stammdatenänderungen geschützt sind (GR-106) |
| `dynamisch` | Name wird im Code berechnet und ist für die automatische Prüfung unsichtbar |

`werkzeuge/regeln.py` prüft in der CI die Aufrufe `store_read`/`store_write`/`store_delete`/`with_lock` im Code gegen
diese Tabelle. Was ein Modul besitzt und liest: `python3 werkzeuge/regeln.py modul <id>`.

**Schnittstellen statt Durchgriff.** Fremde Daten werden über Funktionen des Eigentümers gelesen oder geschrieben:

| Nutzer | Funktion des Eigentümers | Eigentümer |
| --- | --- | --- |
| CRM | `customers_load()`, `vertreter_load()`, `kundengruppen_load()`; Angebotsnamen über `customer_offers()`, `offer_def()` | Verwaltung, Angebot |
| HR | `users_load()`, `nutzer_hat_zugang()`, `mitarbeiter_ohne_zugang_anlegen()` | Plattformkern |
| Bestand (`master_save`) | `stammdaten_speichern()` (`module/verwaltung/import.php`) | Verwaltung |
| Importzentrale | Importverträge `module/<modul>/import.php` der Eigentümer | jeweiliges Modul |

Regeln für eigene Änderungen:

- Neues Dokument → im selben PR in `regeln/datenverantwortung.toml` eintragen (die CI lehnt sonst ab) und
  `python3 werkzeuge/doku.py erzeugen` für [referenz/daten.md](referenz/daten.md).
- Neuer Querzugriff (neuer `leser`/`schreiber`) ist koordinationspflichtig: eigener PR mit Abschnitt „Koordination“.
- Ändert der Eigentümer eine Schnittstelle, nennt der PR alle Nutzer und erweitert nur (alte Aufrufe bleiben gültig).
- Historische Vorgänge (Bestellwünsche, CRM-Aktivitäten, Versionen, Preisverlauf) speichern Schnappschüsse; spätere
  Stammdatenänderungen dürfen sie nicht verändern (GR-106).

Stand: 2026-10-24
