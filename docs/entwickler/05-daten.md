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
Länder- und Ortsdatenbank (`geo/`) und die **Dateiablage** (`daten/dateien/`, `lib/dateiablage.php`): hochgeladene Dateien
der Module als `<bereich>/<xx>/<id>.bin` – in beiden Speicherarten im Dateisystem, nie als `*.php` (die Werkzeuge für
Sicherungsprüfung und Umschalten behandeln nur `*.php` als Dokumente); unvollständige Uploads unter `dateien/.teile/*.tmp`
(nicht gesichert, nach 24 h entfernt). Die Metadaten (Name, Größe, SHA-256, wer, wann) stehen im Dokument des Moduls.

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
im Dokument `sicherung` (Anzeige unter „Sicherheit“). Die Dateiablage `daten/dateien/` ist Teil des Archivs – mit
hochgeladenen Dateien wächst die Sicherung entsprechend.

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

> **Kundensatz:** `kunde_save` (`aktionen/kundenverwaltung.php`) baut den Kundensatz aus `CUSTOMER_FIELDS` neu auf und
> hängt danach alle übrigen Felder des alten Satzes wieder an (`$row += array_diff_key($old, …)`) – so bleiben z. B. die
> Daten der Warenwirtschaft (`wawi`) beim Speichern im Dialog erhalten. Felder aus `CUSTOMER_FIELDS`, die die Anfrage
> nicht enthält, bleiben unverändert.

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
`savedAt`, `savedBy`, `rev`; das veröffentlichte Angebot `publishedAt` (streng steigend mit Millisekunden,
`JJJJ-MM-TTThh:mm:ss.mmmZ`; ältere Stände ohne Millisekunden bleiben gültig – verglichen wird nur auf Gleichheit).
`meta.week` ist eine ISO-Kalenderwoche: KW 53 nur in Jahren mit 53 Wochen (`kw_gueltig`); der Entwurf behält eine
ungültige Angabe, Veröffentlichen lehnt sie ab. Jede Veröffentlichung legt das vorige Angebot
als `versionen/<JJJJMMTT-hhmmss>-<hex>` ab (höchstens `keep_versions`) und den Preisverlauf `historie/<id>`.

```json
{"meta": {"week": 2, "year": 2026, "notice": "", "title?": "…", "source?": "…", "sheetName?": "…",
          "werbung?": {"std": {"titel": "Aktion der Woche", "text?": "…", "artikel": [{"id": "i1", "text?": "Top-Preis"}]}}},
 "sections": ["Frischfleisch"],
 "groups": [{"id": "g1", "name": "Rind", "section": "Frischfleisch", "vk?": "1600"}],
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
| `variants?` | Einträge je Angebots-ID: `{status: value|request|hidden, value?, carried?}`; unter `std` nur `{status: hidden}` = nicht im Wochenangebot; in Angeboten mit eigener Artikelliste macht ein Eintrag `value`/`request` den Artikel zum Teil des Angebots, in Angeboten, die dem Wochenangebot folgen, blendet `hidden` ihn aus; Schlüssel gelöschter Angebote fallen weg |
| `sale?` | Sonderpreis „solange der Vorrat reicht“: Grundpreis `value`, je Angebot abweichend `{value}` oder `{status: none}` |
| `cell?`, `nameRaw?` | Zelladresse und Originaltext der Excel-Datei (intern) |
| `meta.werbung?` | Werbung je Angebots-ID (`std` oder Kundenangebot): `titel` (≤ 80 Zeichen), `text?` (≤ 240), `artikel` = höchstens 12 Artikel-IDs in Reihenfolge mit `text?` (Hinweis, ≤ 40); unbekannte Angebote/Artikel und doppelte fallen weg (`clean_werbung`), keine Übernahme durch Angebote, die dem Wochenangebot folgen; `offer_resolve` liefert nur den Eintrag des jeweiligen Angebots und nur ausgelieferte Artikel (`meta.werbung = {titel, text?, artikel}`); ältere Fassungen verwerfen das Feld |
| Gruppe `vk?` | VK-Gruppe (Stammdaten), aus der „Artikel hinzufügen“ die Angebotsgruppe wählt; `^[0-9A-Za-z._-]{1,10}$`, intern (`offer_resolve` entfernt sie); ältere Fassungen verwerfen das Feld |

Grenzen: höchstens 5000 Artikel und 1000 Gruppen; IDs `^[A-Za-z0-9_-]+$`; Artikelnummer `^[0-9A-Za-z./-]+$`.
`variants`, `sale`, `cell` und `meta.werbung` verlassen den Server nie roh – `offer_resolve()` löst sie je Angebot auf und entfernt sie
(GR-001, GR-002, GR-005).

**`angebote`**: Kundenangebote.
`{"rev": 4, "offers": [{"id": "kunde-a", "name": "Wochenangebot Kunde A", "fallback": "standard", "gruppen?": ["10"]}], "stdPublic": true, "geloescht?": ["alt-id"], "updatedAt": "…", "updatedBy": "…"}`.
`fallback`: `hidden` = eigene Artikelliste (nur Artikel mit eigenem Eintrag in `variants`, auch Sonderposten nur dann; Voreinstellung
für neue Angebote), `standard` = folgt dem Wochenangebot (bisher: alle Artikel des Wochenangebots, ohne eigenen Preis mit
dem Standardpreis). `gruppen`: Kundengruppen,
deren Kunden das Angebot ohne eigene Freischaltung sehen (je Gruppe höchstens ein Angebot). Fehlt das Dokument, gelten
`OFFER_DEFAULTS`. Neue IDs dürfen nicht mit `e-` beginnen (Einzelangebote) und nicht nur aus Ziffern bestehen.
`geloescht`: IDs gelöschter Angebote – sie werden nie wieder vergeben (`offers_save` hängt bei einem neuen Angebot mit
gesperrter ID `-2`, `-3` … an), weil unter der alten ID noch Kundenpreise, Sonderpreise (veröffentlichtes Angebot,
Historie) und direkte Freischaltungen bei Kunden stehen können; gesperrt sind auch solche Reste aus der Zeit vor dem Feld
(`angebot_ids_mit_resten`). Fehlt `fallback` in einer Anfrage, bleibt die gespeicherte Einstellung (neue Angebote: `hidden`); Felder, die
`offers_save` nicht kennt, bleiben erhalten (GR-006).

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
`kunde_save` ändert nur, was die Anfrage enthält: fehlende Felder (auch `angebote`, `active`, `mailAngebot`) bleiben,
fehlendes `login` lässt den Zugang unverändert (entfernt wird er nur mit `login: null` oder `{remove: true}`), ein
leerer Text leert das Feld; Felder, die dieser Stand nicht kennt, bleiben erhalten (GR-006).

Aus dem Kundenimport (Kundendaten-Export der Warenwirtschaft, `kunden_import_lauf` in `module/verwaltung/import.php`):

```json
"wawi": {"alpha": "TESTFIRMA", "konto": "10001", "rgEmpf": "10002", "kondition": "1", "letzteRechnung": "2026-09-14",
         "letzterLieferschein": "2026-09-12", "angelegtAm": "2019-02-03", "angelegtUm": "09:05", "angelegtVon": "TST",
         "kreditlimit": 3000, "umsatzMonat": 1234.5, "rohgewinnMonat": -12.3, "umsatzJahr": 12345.67, "gln": "4000000000017",
         "rgSperre": false, "abgabeCitti": true, "dfb": false, "mailAB": "ab@example.invalid", "weitereEmails": "…",
         "stand": "2026-10-28T12:00:00Z"},
"autoInaktiv": {"seit": "…", "grund": "keine Rechnung seit 18 Monaten (letzte 12.03.2024)"},
"aktivVonHand": "…"
```

- `wawi`: alle weiteren Spalten des Exports (Felder und Typen: `KUNDEN_WAWI_FELDER`), nur nicht leere, gültige Werte;
  `stand` = letzte Änderung durch einen Import. Ein Import setzt bzw. leert nur die Felder, deren Spalte die Datei enthält
  (`wawiFelder`). Ausgeliefert nur an Nutzer mit `kunden.bearbeiten` (`customer_public($c, true)`), nie an CRM, Kunden,
  E-Mail-Antworten oder ins Protokoll (dort nur die Anzahl).
- `autoInaktiv`: vom Import deaktiviert (Aktiv-Regel: keine Rechnung, kein Lieferschein und keine Neuanlage in
  `KUNDEN_AKTIV_MONATE` = 18 Monaten, oder „*“ in der Warenwirtschaft). Nur so gekennzeichnete Kunden aktiviert ein
  späterer Import wieder. `kunde_save` entfernt das Kennzeichen, sobald der Kunde aktiv ist oder der Status von Hand
  geändert wird.
- `aktivVonHand`: von Hand wieder aktiviert (`kunde_save`, Wechsel inaktiv → aktiv); der Import deaktiviert den Kunden
  dann nicht erneut, bis er von Hand deaktiviert wird. Kunden mit aktivem Zugang und Anmeldung in den 18 Monaten
  bleiben ebenfalls aktiv.

**`kundengruppen`**, **`vkgruppen`**, **`vertreter`**: je Liste `{"rev": 2, "groups": [{"nr": "10", "name": "…", …}], "updatedAt": "…", "updatedBy": "…"}`;
Felder je Liste in `GRUPPEN_LISTEN` (`lib/kunden.php`): Kunden- und VK-Gruppen `name`, `klasse`, `kategorie`;
Vertreter `name`, `kurz`, `telefon`, `plz`, `ort`, `land`. Nummer `^[0-9A-Za-z._-]{1,10}$`, höchstens 2000.
Gespeichert wird immer die ganze Liste (fehlende Nummern entfallen); je Eintrag bleiben nicht gesendete Felder und
unbekannte Felder der gespeicherten Fassung erhalten (`gruppen_clean` mit `$alt`), ebenso weitere Felder des Dokuments.

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
 "incoming": [{"code": "1002", "name": "Testartikel 2", "lot": "", "marke": "", "arrival": "2026-01-09", "kg": 300.0,
               "mhd?": "2026-02-20", "kolli?": 12, "ek?": 7.9}]}
```

`ek` (Einkaufspreis €/kg) geht nur an Nutzer mit `bestand.einkaufspreise` (`stock_ohne_ek`). Nur Artikel mit Bestand
über 0 kg werden gespeichert. Erwartete Zugänge (Status „erfasst“) tragen seit 28.10.2026 wie die Partien MHD, Kolli und EK –
optional, nur wenn in der Liste vorhanden (ältere Stände ohne diese Felder bleiben gültig, GR-006). Wochenpreise und Zugänge: [bestand-wochenpreise.md](../bestand-wochenpreise.md).

### HR (`module/hr/urlaub.php`)

Mitarbeiter sind die Nutzer der Plattform (`users_load()`); HR speichert nur eigene Angaben.

- **`hr-personal`**: `{"rev": 3, "personen": [{"id": "u0123456789ab", "nutzer": "u0123456789ab", "vorname": "…", "nachname": "…", "abteilung": "Lager", "pos": 10, "arbeitstage": [1,2,3,4,5], "aktiv": true, "jahre": {"2026": {"anspruch": 30, "uebertrag": 2.5}}, "personalnummer": "", "geaendert": "…"}]}`.
  Ohne gespeicherte Angaben gelten Standardwerte; Einträge ohne Mitarbeiter bleiben als Altbestand lesbar.
- **`hr-abwesenheiten`**: `{"rev": 9, "eintraege": [{"id": "a0123456789ab", "person": "u…", "art": "U", "von": "2026-03-02", "bis": "2026-03-06", "status": "beantragt", "notiz": "", "vertretung": null, "quelle": "antrag", "erfasst": {"t": "…", "by": "…", "byId": "u…"}}]}`.
  `art`: `U` Urlaub, `K` Krank, `G` Gleittag, `X` freier Tag. `status`: `beantragt`, `genehmigt`, `abgelehnt`,
  `zurueckgezogen`, `storniert` – Einträge werden nie gelöscht, nur der Status ändert sich (mit
  `entscheidung: {t, by, grund}`). `quelle`: `antrag`, `personalstelle`, `zeiterfassung`; optional `geaendert`,
  `urlaubAbzug` (in der Zeiterfassung vom Urlaub abgezogene Krankheit – nur Hinweis für die Personalstelle; Krankheit
  zählt in `hr_konto` nie gegen den Urlaub, Inhaber 30.10.2026). Überschneidungen (`hr_kollision`) gelten nur zwischen aktiven
  Einträgen derselben Gruppe: Abwesenheiten (U/K/G) untereinander und freie Tage (X) untereinander – ein freier Tag in
  einer Urlaubswoche zählt dort nur nicht mit.
- **`hr-einstellungen`**: `{"rev": 1, "sperren": [{"von": "…", "bis": "…", "text": "Inventur"}], "ferien": [ … ], "uebertragBis": "03-31", "antraege": true}` – `uebertragBis` (Verfallstag des Resturlaubs, Monat-Tag) ist optional; fehlt es, gilt der 31.03. `antraege` (Schalter „Urlaubsanträge über die Plattform“, Verwaltung → Urlaub, Aktion `hr_antraege_save`) ist optional; nur `false` schaltet Anträge aus, fehlt es, sind sie eingeschaltet.
- **`hr-korrekturen`**: `{"rev": 2, "meldungen": [{"id": "k0123456789ab", "person": "u…", "von": "2026-09-09", "bis": "2026-09-11", "eintrag": "a…", "text": "…", "status": "offen", "erfasst": {"t": "…", "by": "…", "byId": "u…"}, "erledigt": {"t": "…", "by": "…", "byId": "u…", "antwort": "…"}}]}` –
  Korrekturmeldungen der Mitarbeiter („Korrektur melden“, Aktion `hr_korrektur`; `von`/`bis`/`eintrag` optional,
  höchstens 20 offene je Person). Die Personalstelle erledigt sie (`hr_korrektur_erledigt`, nie die eigene); Meldungen
  werden nie gelöscht. Sichtbar nur für die Person selbst und `hr.verwalten`; das Protokoll enthält den Text nicht.

### CRM (`module/crm/crm.php`)

Kundenstammdaten liest das CRM nur über Funktionen der Verwaltung; eigene Dokumente (alle unter der Sperre `crm-kunden`):

- **`crm-kunden`**: `{"rev": 5, "updatedAt": "…", "eintraege": {"k0123456789ab": {"segment": "Gastronomie", "phase": "Angebot", "kontakte": [{"name": "…", "funktion": "…", "telefon": "…", "email": "…"}], "anrufStatus": "Offen", "wiedervorlage": "2026-01-12", "geaendert": "…", "geaendertVon": "…"}}}`.
  Schlüssel = Kunden-ID der Verwaltung oder Interessenten-ID (`i…`). `crm_kunde_save` ändert nur die mitgeschickten
  Felder (`array_merge` mit dem gespeicherten Blatt); fehlende liefert beim Lesen `crm_standard()`. Alle Felder mit Prüfung: `crm_felder()`.
- **`crm-interessenten`**: `{"rev": 2, "updatedAt": "…", "liste": [{"id": "i0123456789ab", "firma": "…", "ansprechpartner": "…", "strasse": "…", "plz": "…", "ort": "…", "land": "…", "telefon": "…", "email": "…", "vertreter": "", "vertreter2": "", "aktiv": true, "erstellt": "…", "erstelltVon": "…", "geaendert": "…", "geaendertVon": "…"}]}`.
- **`crm-aktivitaeten`**: `{"rev": 40, "updatedAt": "…", "liste": [{"id": "a…", "key": "k…", "art": "Telefonat", "notiz": "…", "naechster": "…", "faellig": "…", "at": "…", "von": "…", "vonId": "u…", "firma": "Testfirma GmbH", "nr": "10001"}]}`.
  `firma` und `nr` sind Schnappschüsse (GR-106); höchstens 50 000 Einträge, die ältesten fallen weg.

### Marketing (`module/marketing/marketing.php`)

Eigene Dokumente, alle unter der Sperre `marketing-beitraege`:

- **`marketing-beitraege`**: `{"rev": 12, "updatedAt": "…", "liste": [{"id": "b0123456789ab", "titel": "…", "status": "freigabe", "prioritaet": "normal", "marke": "standard-fleisch", "kanaele": ["instagram"], "format": "reel", "saeule": "wissen", "kampagne": "k…", "verantwortlich": "u…", "verantwortlichSchnappschuss": "…", "drehtermin": "2026-11-02", "produktionBis": "2026-11-04", "veroeffentlichung": "2026-11-06T18:30", "hook": "…", "text": "…", "hashtags": "…", "cta": "…", "notizen": "…", "checkliste": [{"text": "…", "erledigt": false}], "links": [{"titel": "…", "url": "https://…"}], "ki": false, "freigabe": {"t": "…", "von": "…", "vonId": "u…"}, "veroeffentlicht": {"instagram": "https://…"}, "ergebnisse": {"instagram": {"reichweite": 1200, "interaktionen": 85, "aufrufe": null}}, "kommentare": [{"id": "c…", "t": "…", "von": "…", "vonId": "u…", "text": "…"}], "verlauf": [{"t": "…", "von": "…", "was": "…"}], "rev": 4, "erstellt": {…}, "geaendert": {"t": "…", "von": "…"}}]}`.
  `rev` je Beitrag schützt vor stillem Überschreiben (409 mit aktuellem Beitrag). `marketing_beitrag_save` prüft und ändert nur
  mitgeschickte, geänderte Felder (`mkt_felder_pruefen`); fehlende ergänzt beim Lesen `mkt_beitrag_leer()`, unbekannte bleiben.
  Namen in `freigabe`, `kommentare`, `verlauf` und `verantwortlichSchnappschuss` sind Schnappschüsse (GR-106).
- **`marketing-kampagnen`**: `{"rev": 2, "liste": [{"id": "k…", "name": "…", "ziel": "…", "von": "…", "bis": "…", "marke": "", "farbe": "#c27a1a", "archiviert": false, "erstellt": {…}}]}`.
- **`marketing-einstellungen`**: `{"marken": [{"id": "standard-fleisch", "name": "…", "farbe": "#8c1d2c", "aktiv": true}], "kanaele": [{"id": "instagram", "name": "Instagram", "limit": 2200, "hashtags": 30, "aktiv": true}], "formate": […], "saeulen": […]}`.
  Ohne Dokument gelten die Grundwerte `mkt_grundwerte()`. Kennungen bleiben beim Umbenennen; neue entstehen aus dem Namen und
  belegen nie eine frühere Kennung (`mkt_liste_pruefen`).

### Controlling (`module/controlling/`)

Aufbau in Bereichen: gemeinsame Grundlage `controlling.php` (Liste `CONTROLLING_BEREICHE`, Monate, Zahlenprüfung), je Bereich
eine eigene Datei mit eigenem Dokument `controlling-<bereich>`, eigenen Rechten `controlling.<bereich>_sehen/_bearbeiten` und
Aktionen `controlling_<bereich>_…`. Geplant sind weitere Bereiche (OP-Konten, Liquidität); bestehende bleiben davon unberührt.

- **`controlling-umsatz`** (vertraulich, `umsatz.php`): `{"rev": 7, "jahre": {"2026": {"01": {"V1": {"kg": 1250.5, "umsatz": 25000, "db": 3500}}}},
  "vertreter": {"V1": {"name": "…", "kurz": "VV"}}, "geaendert": {"t": "…", "von": "u…", "vonName": "…"}}`. Monate als „01“–„12“,
  Werte `null` = leer; ein Vertreter ohne Werte wird nicht gespeichert, ein Monat ohne Werte entfällt. Speichern ändert nur die
  mitgeschickten Vertreter (aktuelle aus den Stammdaten); Werte ausgeschiedener Vertreter bleiben, ihr Name kommt aus dem
  Schnappschuss `vertreter` (GR-106). `rev` schützt vor gleichzeitigem Überschreiben (409).

### Leergut (`module/leergut/leergut.php`)

Vorzeichen überall: **+ der Partner schuldet uns, − wir schulden dem Partner**; eine Bewegung zählt Abgang positiv, Zugang negativ.
Mengen sind Zuordnungen Lademittel → ganze Stückzahl (`{"e2": 40, "h1": 2}`), Nullen werden nicht gespeichert.

- **`leergut-stamm`**: `{"rev": 3, "lademittel": [{"id": "e2", "name": "E2-Kiste", "wert": 5.5, "aktiv": true}],
  "partner": [{"id": "p…", "name": "…", "art": "spedition", "mandant": "standard", "kontoNr": "", "kundenNr": "", "fristTage": 14, "email": "",
  "ansprechpartner": "", "lieferanten": "", "notiz": "", "lademittel": ["e2", "h1"], "aktiv": true, "rev": 2, "erstellt": {…}, "geaendert": {…},
  "quelle": "import|winab"?}]}`. `kundenNr` = WinAB-Kundennummer (nur Ziffern, eindeutig; ohne Angabe beim Ändern bleibt sie), `quelle: "winab"` =
  beim WinAB-Import angelegt (Name „Name (Kd.-Nr.)“, Art `kunde`). `winab` (nach einem WinAB-Bericht):
  `{"ersteLieferung": "…", "letzteLieferung": "…", "letzteRueckgabe": "…", "bis": "<Berichtsdatum>"}` – laut Bericht, auch aus reinem Tausch
  (Belege ohne Wirkung auf den Saldo werden nicht gebucht); spätere Berichte führen es fort (erste = früheste, letzte = späteste Angabe).
  Ohne Dokument gelten die Grundwerte `lg_grund_lademittel()` (E2 5,50 €, H1 36,00 €, übrige ohne Wert). Lademittel werden nie
  entfernt, nur deaktiviert (sonst wären Buchungen nicht mehr lesbar); neue Kennungen entstehen aus dem Namen.
- **`leergut-bewegungen`** (Historie): `{"rev": 9, "liste": [{"id": "b…", "partner": "p…", "datum": "2026-10-26", "typ": "bewegung",
  "abgang": {"e2": 63}, "zugang": {}, "beleg": "", "text": "", "quelle": "hand|import|winab", "erfasst": {"t": "…", "von": "…", "vonId": "u…"},
  "storno": null, "winab": {"kd": "9100001", "art": "Lieferschein", "beleg": "500001"}?}]}`. `winab` (nur bei `quelle: "winab"`) ist der
  Schlüssel für den Abgleich mit dem nächsten Bericht. Nur anhängen; Stornieren setzt `storno: {t, von, vonId, grund}`, die Bewegung zählt dann nicht mehr.
- **`leergut-abstimmungen`** (Historie): `{"liste": [{"id": "a…", "partner": "p…", "stichtag": "…", "eingang": "…", "fristBis": "…",
  "saldo": {"e2": -15}, "status": "offen|bestaetigt|widersprochen|info", "quelle": "", "notiz": "", "eigen": {…}, "verlauf": [{t, von, was}],
  "rev": 2, "herkunft": "import"?}]}`. `saldo` = Saldo laut Partner in unserem Vorzeichen; `eigen` = unser Saldo zum Stichtag beim
  Speichern (Schnappschuss, GR-106). Die Oberfläche bekommt zusätzlich `eigenJetzt`, `differenz`, `ampel` und `restTage` (berechnet).
  „Bestätigt“ im Konto ist unser Saldo bis zum Stichtag des letzten bestätigten Auszugs.
- **`leergut-abschreibungen`**: `{"liste": [{"id": "d…", "zugestellt": "…", "auftrag": "", "empfaenger": "…", "empfaengerNr": "", "ort": "",
  "sendung": "", "menge": {"e2": 5}, "grund": "", "status": "offen|widersprochen|berechnet|ausgeglichen|ignoriert", "rechnung": "",
  "notiz": "", "verlauf": […], "rev": 1, "quelle": "dachser"?}]}`. `quelle: "dachser"` = aus der Dachser-Liste (`leergut_dachser_import`,
  Recht `leergut.bearbeiten`, Text der Mail oder .eml in `text`, `vorschau: true` schreibt nichts); abgeglichen über `sendung`.
- **`leergut-inventur`**: `{"liste": [{"id": "i…", "stichtag": "…", "positionen": [{"name": "Lager (WinAB-Inventur)", "werte": {"e2": 2289}}],
  "notiz": "", "rev": 1}]}` – eigener Bestand für die Bilanz (letzte Inventur bis zum Stichtag).

Datenpaket (`leergut_import`, nur mit `leergut.verwalten`): `{"format": "stafl-leergut", "version": 1, "lademittel": […], "partner":
[{"schluessel": "…", "name": "…", …}], "bewegungen": [{"partner": "<schluessel>", …}], "abstimmungen": […], "abschreibungen": […],
"inventur": […]}` – geprüft mit denselben Regeln wie die Eingabemasken; mit Fehlern wird nichts übernommen, in ein Modul mit Daten
nur mit `ersetzen`. Echte Pakete liegen nie im Repository (GR-007); Beispiel: `tests/fixtures/leergut/datenpaket.json`.

WinAB-Bericht (`leergut_winab_import`, nur mit `leergut.verwalten`, `vorschau: true` schreibt nichts): `{"bericht": {"datei": "…", "von": "2026-01-01",
"bis": "<Berichtsdatum>"}, "kunden": [{"nr": "9100001", "name": "…"}], "belege": [{"kd": "9100001", "art": "Lieferschein|Gutschrift|Rechnung",
"beleg": "500001", "datum": "…", "abgang": {"e2": 21}, "zugang": {"e2": 20}}]}` – `kunden` nennt alle Kunden des Berichts
(je Kunde optional `ersteLieferung`, `letzteLieferung`, `letzteRueckgabe` im Berichtszeitraum). Abgleich je
Kunde, Belegart und Belegnr. nur im Zeitraum und für diese Kunden; geänderte Belege werden storniert und neu gebucht, fehlende storniert
(Grund „WinAB-Abgleich vom …“). Der Bericht bleibt im Browser; gespeichert werden nur die Buchungen.

### REWE (`module/rewe/rewe.php`, in Prüfung)

Kalenderwochen sind ISO-Wochen „JJJJ-WW“ und meinen die **Lieferwoche**. Mengen sind Zuordnungen Artikel → ganze Stückzahl
(`{"rb": 2, "fk": 1}`, 1 Stück = 1 Kolli). Alle Schreibvorgänge laufen unter der Sperre `rewe-maerkte`.

- **`rewe-stamm`**: `{"rev": 2, "lieferwege": [{"id": "l…|direkt", "name": "…", "art": "lager|direkt", "bestellschluss": "Freitag früh der Vorwoche",
  "aktiv": true}], "artikel": [{"id": "rb", "name": "Roastbeef Dry Aged", "einheit": "Stück", "nr": "<WinAB-Artikelnummer>", "aktiv": true}],
  "team": {"u…": {"alle": true, "export": false}}}`. Ohne Dokument gelten Direktbelieferung und die Artikel Roastbeef, Filetkopf, Vac. Set.
  Lieferwege und Artikel werden nie entfernt, nur deaktiviert. `team` ist die Zuweisung im Modul („alle Listen“, „Wochenabschluss“)
  und wirkt zusätzlich zu den Rechten `rewe.alle` und `rewe.exportieren`.
- **`rewe-maerkte`**: `{"rev": 5, "liste": [{"id": "m…", "rev": 3, "kdNr": "<WinAB-Kd.-Nr.>", "reweNr": "", "name": "…", "strasse": "", "plz": "",
  "ort": "…", "region": "", "telefon": "", "kauf": "regelmaessig|gelegentlich|interessiert|kein_interesse|ruhend|ausgelistet",
  "zustaendig": [{"ab": "2026-01", "nutzer": "u…|"}], "lieferweg": [{"ab": "2026-01", "id": "l…"}], "dauer": {"rhythmus": 0-4,
  "mengen": {…}, "ab": "JJJJ-WW", "pauseBis": ""}, "abfragetag": "mo…fr|", "ansprechpartner": [{"name": "…", "rolle": "", "telefon": "",
  "email": ""}], "hinweis": "", "erstellt": {…}, "geaendert": {…}}]}`. `zustaendig` und `lieferweg` sind „ab KW“-Historien (gilt der
  letzte Eintrag mit `ab` ≤ KW). Steht die Kd.-Nr. im Kundenstamm der Verwaltung, kommen Name, Anschrift und Telefon von dort.
- **`rewe-wochen/<Jahr>`** (ein Dokument je ISO-Jahr): `{"rev": 9, "maerkte": {"m…": {"45": {"s": "bestellt|kein|ne|pause", "m": {"rb": 2},
  "ob": true?, "n": "<Notiz>"?, "lw": "l…", "zu": "u…", "zuName": "…", "q": "hand|dauer|excel", "r": 2, "t": "…", "von": "…", "vonId": "u…",
  "nachtrag": true?}}}, "abschluss": {"45": {"exportiert": {"t", "von", "vonId", "zeilen", "stueck"}, "erfasst": {"t", "von", "vonId"}}}}`.
  `lw`, `zu` und `zuName` sind der Schnappschuss beim Antworten (GR-106); `r` schützt vor gleichzeitigem Überschreiben (409);
  `nachtrag` = nach dem Excel-Export geändert.
- **`rewe-verlauf`**: `{"rev": 4, "liste": [{"id": "n…", "markt": "m…", "art": "notiz|telefonat|besuch|reklamation|ohne_berechnung|system",
  "text": "…", "wv": "JJJJ-MM-TT|", "erledigt": {"t", "von"}|null, "q": "hand|datenpaket", "t": "…", "von": "…", "vonId": "u…"}]}` – `system`
  schreibt nur der Server (Anlage, Kaufbereitschaft, Dauerauftrag, Zuweisung).

Datenpaket (`rewe_import`, nur mit `rewe.verwalten`, `vorschau: true` schreibt nichts): `{"format": "stafl-rewe", "version": 1,
"lieferwege": [{"id", "name", "art", "bestellschluss"?}], "artikel"?: […], "maerkte": [{"kdNr", "name", …, "zustaendig": [{"ab", "liste"}],
"lieferweg": [{"ab", "id"}], "wochen": {"JJJJ-WW": {"s", "m", "n"}}, "notizen": [{"art", "text"}]}]}` plus `zuordnung` (Listenname →
Nutzer-ID). Mit Fehlern wird nichts übernommen, in ein Modul mit Daten nur mit `ersetzen` (das Team bleibt). Echte Pakete liegen nie
im Repository (GR-007); Beispiel: `tests/fixtures/rewe/datenpaket.json`.

### Qualitätssicherung · QM-System (`module/qs/qs.php`, in Entwicklung)

Löst die Excel „QM-System“ ab (Blätter Inhaltsverzeichnis, Managementsystem, Prüfungen). Alle Listen-Dokumente haben die Form
`{"rev": N, "liste": [...]}`; jeder Eintrag hat einen eigenen Stand `rev` (veralteter Stand → 409 `konflikt`). Alle Schreibvorgänge
laufen unter der Sperre `qs-dokumente`. Zuständig/Vertreter sind **Kürzel** (Schnappschuss, GR-106); Namen in `erstellt`, `geprueft`,
`freigegeben`, `verlauf` sind Schnappschüsse `{"t", "von", "vonId"}`.

- **`qs-stamm`**: `{"rev", "kapitel": [{"id": "1.4", "titel", "zustaendig", "vertreter", "aktiv"}], "personen": [{"id": "<Kürzel>", "name",
  "funktion", "mitarbeiter": "<Nutzer-ID>|", "aktiv"}], "einstellungen": {"ueberpruefungMonate": 36}}`. Ein Mitarbeiter ist mit höchstens
  einem Kürzel verknüpft; verwendete Kapitel werden nur deaktiviert.
- **`qs-dokumente`**: `{"id": "d…", "rev", "kapitel", "art": "A|F|L|E|V|X|O", "nr": "1.4-F08", "titel", "ablage": "<Pfad>|https://…",
  "zustaendig", "vertreter", "notiz", "eingezogen": {"t", "von", "vonId", "grund"}|null, "ueberprueft": {"t", "von", "vonId", "notiz"}?,
  "versionen": [{"id": "v…", "nr": 3|null, "datum": "JJJJ-MM-TT|", "status": "entwurf|pruefung|geprueft|freigegeben|ersetzt|verworfen",
  "aenderungen", "grund", "erstellt", "bearbeiter": ["<Nutzer-ID>"], "geprueft", "freigegeben", "kuerzel": {"erstellt", "geprueft",
  "freigegeben"}|null, "quelle": "hand|paket", "verlauf": […]}], "verlauf": […]}`. Gelenkt sind A, F, L, E, V; Ordner (O) und externe
  Dokumente (X) haben keine Versionen. Die Versionsnummer entsteht erst bei der Freigabe (höchste + 1), `datum` = Freigabetag; die
  vorige gültige Version wird `ersetzt`. Wer in `bearbeiter` steht, prüft nicht (4-Augen-Prinzip, serverseitig). Die Antwort ergänzt
  `zustand` (`gueltig|entwurf|pruefung|ohne|eingezogen|register`) und `ueberpruefung` (`{"seit", "faelligAb", "faellig"}` – seit der
  letzten Freigabe bzw. `ueberprueft`, nach `ueberpruefungMonate`).
  **Dokumentenablage** (optional, seit Bauabschnitt 2): `dateien: [{"id": "<20 Hex>", "name", "art": "pdf|docx|…", "mime", "groesse",
  "sha256", "hochgeladen": {"t", "von", "vonId"}, "nachgetragen": true?, "entfernt": {"t", "von", "vonId", "grund"}?}]` je Version
  (gelenkt) bzw. am Dokument (Ordner, extern); die Datei selbst liegt in der Dateiablage (Bereich `qs`). Im Entwurf (`qs.bearbeiten`,
  wer ablegt oder löscht, kommt in `bearbeiter`) wird endgültig gelöscht; sonst nur `entfernt` vermerkt (freigegebene/ersetzte Versionen
  nur mit `qs.freigeben`, mit Grund). In Prüfung, verworfen oder eingezogen: keine Änderung (409); höchstens 50 Dateien je Stelle.
- **`qs-handbuch`**: `{"id": "h…", "rev", "kapitel", "pos", "nr": "2.0.14", "titel", "text", "verweise": ["1.3-L02 HACCP-Analyse"], "ifs",
  "zustaendig", "vertreter", "entfallen": {…}|null, "aenderungen": [{"datum", "was", "grund", "von"}]}`. Ein Abschnitt „Ziel“ steht in der
  Oberfläche als Einleitung des Kapitels.
- **`qs-pruefplan`**: `{"id": "p…", "rev", "kapitel", "titel", "beschreibung", "intervall": "arbeitstaeglich|taeglich|woechentlich|monatlich|
  quartal|halbjahr|jaehrlich|zweijaehrlich|dreijaehrlich|anlass", "start": "JJJJ-MM-TT|", "womit", "sollwert", "massnahme", "zustaendig",
  "vertreter", "ausfuehrende": ["<Nutzer-ID>"], "aktiv", "verlauf"}`. Die Antwort ergänzt `faellig`: Kalender-Intervalle (`art: kalender`)
  zählen jede vergangene Periode ohne Nachweis als versäumt (`versaeumt` neueste zuerst, `versaeumtAnzahl`, `quote` über 30 Tage / 12 Wochen /
  12 Monate, `offen` = laufende Periode ohne Nachweis); arbeitstäglich = Mo–Fr ohne Hamburger Feiertage (`hr_feiertag`). Rollende Intervalle
  (`art: rollend`) rechnen ab dem letzten Nachweis, sonst ab `start`, sonst sofort fällig. `monate` = die letzten 6 Monate und der laufende
  (`{"m", "faellig", "erfuellt", "abweichung"}`).
- **`qs-nachweise`**: `{"id": "n…", "pruefung", "datum", "ergebnis": "io|abweichung", "bemerkung", "durch", "massnahme": "m…|", "erfasst",
  "storno": {"t", "von", "vonId", "grund"}|null}` – nie geändert oder gelöscht. Mit nur `qs.nachweis` nur für zugewiesene Prüfungen
  (`ausfuehrende` oder eigenes Kürzel als Zuständig/Vertreter) und nur eigene stornieren.
- **`qs-massnahmen`**: `{"id": "m…", "nr": "2026-001", "rev", "quelle": "intern|extern|kunde|behoerde|pruefung|reklamation|review|sonstige", "bezug", "kapitel",
  "anforderung", "bewertung": "|A|B|C|D|Major|KO", "anforderungText", "feststellung", "korrektur", "korrekturVerantwortlich",
  "korrekturFrist", "korrekturErledigt", "nachweisDoku", "ursache", "massnahme", "zustaendig", "frist", "erledigtAm",
  "status": "offen|in_arbeit|umgesetzt|wirksam|verworfen", "freigabeVon", "freigabeDatum", "freigabeNotiz",
  "wirksamkeit": {"t", "von", "vonId", "notiz"}|null, "pruefung": "p…|", "nachweisId": "n…|", "erfasst", "geaendert", "verlauf"}` – Aufbau
  des IFS-Maßnahmenplans; `wirksam`/`verworfen` nur mit `qs.freigeben` und Notiz.

Datenpaket (`qs_import`, nur mit `qs.verwalten`, `vorschau: true` schreibt nichts): `{"format": "stafl-qs", "version": 1, "kapitel", "personen",
"dokumente": [{… , "versionen": [{"nr", "datum", "aenderungen", "grund", "erstellt", "geprueft", "freigegeben"}]}], "handbuch", "pruefungen",
"massnahmen"}` – die höchste Version gilt, ältere sind `ersetzt`; Verknüpfungen mit Mitarbeitern und Zuweisungen enthält das Paket nicht.
Mit Fehlern wird nichts übernommen, in ein Modul mit Daten nur mit `ersetzen` (Einstellungen bleiben, Nachweise werden geleert); sobald in
der Dokumentenablage Dateien liegen, gar nicht mehr (409 – die Dateien gingen sonst verloren; die Vorschau nennt `dateien`). Echte Pakete
liegen nie im Repository (GR-007); Beispiel: `tests/fixtures/qs/datenpaket.json`.

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
| Marketing | `users_load()`, `may()` (Verantwortliche = Mitarbeiter mit `marketing.bearbeiten`) | Plattformkern |
| Controlling | `vertreter_load()` (Nummer, Name, Kürzel für die Umsatzstatistik) | Verwaltung |
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
