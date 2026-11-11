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
`cell`, `variants`, `sale`, `namen` nur bei Bedarf; `clean_master` ebenso `vkGruppe`, `gtin`, `nameWawi` und `namen`:

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
Über dieselbe Aktion: `darstellung` (`'einfach'` | `'effekte'`; fehlt = automatisch) und `leiste` (`'fest'`; fehlt =
schmal, klappt bei Bedarf auf – Pin der Seitenleiste, `rahmen.js`, seit 10.11.2026). Alle drei Felder sind optional;
ältere Versionen ignorieren sie.

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
| `zugang?` | nur `false` = Mitarbeiter ohne Anmeldung (z. B. Lager, Zeiterfassung); dann immer `active: false` |
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
          "werbung?": {"std": {"titel": "Aktion der Woche", "text?": "…", "artikel": [{"id": "i1", "text?": "Top-Preis"}],
                               "weitere?": [{"titel": "Zweite Aktion", "artikel": [{"id": "i2"}]}]}}},
 "sections": ["Frischfleisch"],
 "groups": [{"id": "g1", "name": "Rind", "section": "Frischfleisch", "vk?": "1600"}],
 "items": [{
   "id": "i1", "code": "1001", "name": "Testartikel Rinderhüfte", "category": "Rind", "origin": "DE",
   "condition": "frisch", "groupId": "g1",
   "price": {"status": "value", "value": 12.5}, "altPrices": [],
   "variants": {"kunde-a": {"status": "value", "value": 11.9}, "std": {"status": "hidden"}},
   "sale": {"value": 9.9, "offers": {"kunde-a": {"status": "none"}, "kunde-b": {"status": "mark"}}, "since": "…"}
 }]}
```

| Feld | Werte |
| --- | --- |
| `category` | `CATEGORIES`: Rind, Kalb, Schwein, Lamm & Schaf, Geflügel, Knochen, Sonstiges (unbekannt → Sonstiges) |
| `condition` | `CONDITIONS`: frisch, gefroren, frisch-gefroren, dry-aged, unbekannt |
| `price`, `altPrices[]` | `{status: value|request|none, value?, raw?, label?}`, `value` 0 bis unter 100 000, 4 Nachkommastellen; höchstens 5 Zusatzpreise |
| `variants?` | Einträge je Angebots-ID: `{status: value|request|hidden, value?, carried?}`; unter `std` nur `{status: hidden}` = nicht im Wochenangebot; in Angeboten mit eigener Artikelliste macht ein Eintrag `value`/`request` den Artikel zum Teil des Angebots, in Angeboten, die dem Wochenangebot folgen, blendet `hidden` ihn aus; Schlüssel gelöschter Angebote fallen weg |
| `sale?` | Empfehlung (bis 11/2026 „Sonderpreis“): Grundwert `value` (Empfehlungspreis = Sonderposten „solange der Vorrat reicht“) oder `mark: true` (ohne Preisänderung, nur hervorheben); je Angebot abweichend `{value}`, `{status: mark}` oder `{status: none}`. `offer_resolve` liefert mit Preis `sale: true` und `regular` (ohne Bestand ausgeblendet), ohne Preis `empfehlung: true` (Preis und Sichtbarkeit unverändert). Ältere Fassungen verwerfen Einträge ohne `value` |
| `cell?`, `nameRaw?` | Zelladresse und Originaltext der Excel-Datei (intern) |
| `namen?` | Eigene Bezeichnung je Kundenangebot: `{<Angebots-ID>: Text ≤ 200}`; fehlt ein Eintrag, gilt `name` (Basiswert, zugleich die Bezeichnung im Wochenangebot – unter `std` gibt es keinen Eintrag); leere Texte und Schlüssel gelöschter Angebote fallen weg (`angebotsnamen_clean`); `offer_resolve` setzt `name` des jeweiligen Angebots und entfernt das Feld; ältere Fassungen verwerfen das Feld (dann gilt überall wieder `name`) |
| `meta.werbung?` | Werbung je Angebots-ID (`std` oder Kundenangebot): `titel` (≤ 80 Zeichen), `text?` (≤ 240), `artikel` = höchstens 12 Artikel-IDs in Reihenfolge mit `text?` (Hinweis, ≤ 40), `weitere?` = eine zweite Werbung im selben Aufbau (höchstens zwei je Angebot, `WERBUNG_BLOECKE`; ältere Fassungen lesen nur die erste); unbekannte Angebote/Artikel und doppelte fallen weg, leere Werbungen ebenso – die nächste rückt nach (`clean_werbung`), keine Übernahme durch Angebote, die dem Wochenangebot folgen; `offer_resolve` liefert nur den Eintrag des jeweiligen Angebots und nur ausgelieferte Artikel (`meta.werbung = {titel, text?, artikel, weitere?}`); ältere Fassungen verwerfen das Feld |
| Gruppe `vk?` | VK-Gruppe (Stammdaten), aus der „Artikel hinzufügen“ die Angebotsgruppe wählt; `^[0-9A-Za-z._-]{1,10}$`, intern (`offer_resolve` entfernt sie); ältere Fassungen verwerfen das Feld |

Grenzen: höchstens 5000 Artikel und 1000 Gruppen; IDs `^[A-Za-z0-9_-]+$`; Artikelnummer `^[0-9A-Za-z./-]+$`.
`variants`, `sale`, `cell`, `namen` und `meta.werbung` verlassen den Server nie roh – `offer_resolve()` löst sie je Angebot auf und entfernt sie
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
{"id": "k0123456789ab", "nr": "10001", "gruppe": "10", "vertreter": "3", "vertreter2": "", "versandart": "2",
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
         "name2": "- Fleischtheke -", "name3": "…", "winabAngebot": "ANGEBOT 1", "verband": "4", "steuernummer": "…",
         "hermesId": "0070000001", "hermesDeckung": 25000, "lademittelbestand": -12, "abPerMail": true,
         "partnerName": "…", "partner1": "…", "partner2": "…", "partnerAbteilung": "…", "partnerEmail": "…", "partnerTelefon": "…", "partnerTelefax": "…",
         "stand": "2026-10-28T12:00:00Z"},
"autoInaktiv": {"seit": "…", "grund": "keine Rechnung seit 18 Monaten (letzte 12.03.2024)"},
"aktivVonHand": "…"
```

- `wawi`: alle weiteren Spalten des Exports (Felder und Typen: `KUNDEN_WAWI_FELDER`; seit 06.11.2026 auch die Spalten des Exports
  „Kundenstammdaten komplett“, `lademittelbestand` als ganze Zahl = Zähler der Warenwirtschaft über alle Lademittel), nur nicht leere, gültige Werte;
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

**`kundengruppen`**, **`vkgruppen`**, **`vertreter`**, **`versandarten`**, **`lieferanten`**, **`abteilungen`**: je Liste `{"rev": 2, "groups": [{"nr": "10", "name": "…", …}], "updatedAt": "…", "updatedBy": "…"}`;
Felder je Liste in `GRUPPEN_LISTEN` (`lib/kunden.php`): Kunden- und VK-Gruppen `name`, `klasse`, `kategorie`;
Vertreter `name`, `kurz`, `telefon`, `plz`, `ort`, `land`; Versandarten `name` (Text); Abteilungen `name` (bis 40 Zeichen,
eindeutig ohne Groß-/Kleinschreibung) und `frueher` (frühere Bezeichnungen, höchstens 10, nur vom Server beim Umbenennen
gepflegt – `abteilungen_pruefen`; HR liest die Liste über `abteilungen_liste`/`abteilung_nach_name`); Lieferanten `name` (Name1, darf fehlen), `kurz`,
`strasse`, `plz`, `ort`, `land`, `landIntrastat`, `telefon`, `gruppe`, `konto`, `kondition`, `vertreter`, `vertreterName`, `versandart`, `gln`,
`lademittelbestand`, `umsatzJahr`, `kwUmsatzLfdJahr`, `kwUmsatzVorjahr`, `angelegtAm` (Texte wie im Export; die drei Umsatzfelder gibt
`lieferanten` nur mit `stammdaten.bearbeiten` aus – `LIEFERANTEN_UMSATZ`). Nummer `^[0-9A-Za-z._-]{1,10}$`, höchstens 2000.
Gespeichert wird immer die ganze Liste (fehlende Nummern entfallen); je Eintrag bleiben nicht gesendete Felder und
unbekannte Felder der gespeicherten Fassung erhalten (`gruppen_clean` mit `$alt`), ebenso weitere Felder des Dokuments.

**`angebotskategorien`** (Verwaltung, seit 05.11.2026): `{"rev": 3, "kategorien": [{"id": "k1a2b3c4d5", "name": "Eigene Zerlegung, Marke \"Fleischmeister\"", "vk": ["1050", "1150"]}], "updatedAt": "…", "updatedBy": "…"}`.
Reihenfolge der Kategorien und darin der VK-Gruppen = Aufbau aller Angebote; jede VK-Gruppe höchstens einer Kategorie,
Bezeichnungen eindeutig, höchstens 100 Kategorien (`module/verwaltung/angebotskategorien.php`, `kategorien_clean`).
Lesen: Aktion `angebotskategorien` mit `stammdaten.sehen` oder `angebot.bearbeiten` (liefert dazu Nummer und Name der
VK-Gruppen), speichern: `angebotskategorien_save` mit `stammdaten.bearbeiten` und Revision. Der Editor ordnet den
Entwurf danach (`OfferCore.nachKategorien`: VK-Gruppe der Angebotsgruppe `groups[].vk`, sonst die häufigste ihrer
Artikel – einmal gemerkt; Abschnitt `section` = Kategorie; Gruppen ohne Kategorie am Ende ohne Abschnitt). Leer =
Reihenfolge von Hand wie früher.

**`stammdaten`**: Artikelstammdaten aus `clean_master()`.
`{"rev": 12, "updatedAt": "…", "updatedBy": "…", "articles": [{"code": "1001", "name": "Testartikel Rinderhüfte", "category": "Rind", "origin": "DE", "condition": "frisch", "vkGruppe?": "200", "gtin?": "4000000000000", "nameWawi?": "Testartikel Hüfte, DE, frisch", "namen?": {"kunde-a": "Rinderhüfte Spezial"}}]}`.
Höchstens 20 000 Sätze, Artikelnummern eindeutig über `code_key()` (führende Nullen und Groß-/Kleinschreibung zählen
nicht), GTIN 8–14 Ziffern. `name` ist die Angebotsbezeichnung (Basiswert), `nameWawi` die Originalbezeichnung der
Warenwirtschaft (Bezeichnung1 des Artikelstammdaten-Imports, nur dort gesetzt; steht in der MHD-Liste), `namen` die eigene
Bezeichnung je Kundenangebot wie beim Artikel des Angebots (Vorgabe für künftige Wochen und neu aufgenommene Artikel).

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

- **`hr-personal`**: `{"rev": 3, "personen": [{"id": "u0123456789ab", "nutzer": "u0123456789ab", "vorname": "…", "nachname": "…", "abteilung": "Lager", "pos": 10, "arbeitstage": [1,2,3,4,5], "aktiv": true, "jahre": {"2026": {"anspruch": 30, "uebertrag": 2.5}}, "personalnummer": "", "verfall": true, "geaendert": "…"}]}`.
  Ohne gespeicherte Angaben gelten Standardwerte; Einträge ohne Mitarbeiter bleiben als Altbestand lesbar.
  `verfall` (seit 03.11.2026, optional): `false` = der Resturlaub aus dem Vorjahr verfällt für diese Person nicht; fehlt
  das Feld oder ist es `true`, verfällt er am Verfallstag (`hr-einstellungen.uebertragBis`).
  `eintritt` (seit 11.11.2026, optional, `JJJJ-MM-TT` oder `null`): erster Arbeitstag. `jahre.*.anspruch` ist der volle
  Jahresurlaub laut Vertrag; vor dem Eintrittsjahr zählt kein Anspruch (und kein Betriebsurlaub vor dem Eintritt), im
  Eintrittsjahr 1/12 je vollem Monat ab dem Eintrittstag (§ 5 BUrlG, Bruchteile ab ½ auf volle Tage, sonst auf ½), bei
  Eintritt vor dem 01.07. mindestens der gesetzliche Mindesturlaub (4 Tage je Wochenarbeitstag, höchstens der volle Anspruch;
  `hr_anspruch_info`). Das Konto nennt `anspruchVoll` und `anteilig` (`monate`, `mindest`, `eintritt`). Gespeichert werden
  Daten ab 1970 bis heute + 3 Jahre (`hr_eintritt_datum`); `''`/`null` entfernt das Datum. Ohne Feld (Vorversion) gilt der
  volle Anspruch – die Vorversion ignoriert das Feld, keine Migration nötig.
  `vertretung` (seit 10.11.2026, optional, Personenkennung oder `null`): feste Vertretung – steht in jedem Antrag der Person
  fest und muss im Zeitraum da sein (`hr_feste_vertretung`; ist sie nicht mehr im Urlaubsplan, wählt die Person wieder selbst).
  `abteilungNr` (seit 10.11.2026, optional, Nummer in `abteilungen` oder `null`): Abteilung aus den Stammdaten; `abteilung`
  bleibt als Name gespeichert (Vorversion). Beim Lesen (`hr_personal` → `hr_abteilung_aufloesen`) gilt der Name aus den
  Stammdaten – über die Nummer, sonst über den Namen bzw. eine frühere Bezeichnung; ohne Treffer der gespeicherte Name.
- **`hr-abwesenheiten`**: `{"rev": 9, "eintraege": [{"id": "a0123456789ab", "person": "u…", "art": "U", "von": "2026-03-02", "bis": "2026-03-06", "status": "beantragt", "notiz": "", "vertretung": null, "quelle": "antrag", "erfasst": {"t": "…", "by": "…", "byId": "u…"}}]}`.
  `vertretung` (Person) ist bei Urlaubsanträgen Pflicht, solange `hr-einstellungen.planung.vertretungPflicht` nicht `false` ist. `art`: `U` Urlaub, `K` Krank, `G` Gleittag, `X` freier Tag, `F` unentschuldigt (seit 03.11.2026, nur Personalstelle; zählt nicht
  gegen den Urlaub, beim Eintragen E-Mail an den Mitarbeiter über `hr_fehlen_mail`). `status`: `beantragt`, `genehmigt`, `abgelehnt`,
  `zurueckgezogen`, `storniert` – Einträge werden nie gelöscht, nur der Status ändert sich (mit
  `entscheidung: {t, by, grund}`). `quelle`: `antrag`, `vorplanung` (seit 10.11.2026: mehrere Zeiträume auf einmal über
  `hr_vorplanung`, sonst wie `antrag`), `personalstelle`, `zeiterfassung`; optional `vertretung2` (zusätzliche Vertretung,
  seit 10.11.2026 – fehlt das Feld: keine), `geaendert`,
  `urlaubAbzug` (in der Zeiterfassung vom Urlaub abgezogene Krankheit – nur Hinweis für die Personalstelle; Krankheit
  zählt in `hr_konto` nie gegen den Urlaub, Inhaber 30.10.2026). Überschneidungen (`hr_kollision`) gelten nur zwischen aktiven
  Einträgen derselben Gruppe: Abwesenheiten (U/K/G/F) untereinander und freie Tage (X) untereinander – ein freier Tag in
  einer Urlaubswoche zählt dort nur nicht mit.
  Sichtbarkeit im Kalender (`hr_monat` → `hr_zeile`, Antwortfeld `sicht`, seit 11.11.2026; `voll` bleibt für ältere Seiten):
  `voll` = Personalstelle (Art, offene Anträge mit „?“, freie Tage „x“; die eigene Zeile sieht jeder so), `kollege` = nur „A“
  (nur genehmigt, nie der Grund), `urlaub` = Recht `hr.kalender` (sensibel, einzeln vergeben), je Zeile nur für Kollegen der
  eigenen Abteilung (`hr_gleiche_abteilung`: `abteilungNr`, sonst Name ohne Groß-/Kleinschreibung; leer nie gleich; ohne
  eigene Person im Urlaubsplan oder ohne Abteilung bei niemandem): genehmigter Urlaub „U“ und Gleittag „G“
  (`HR_KALENDER_ARTEN`), alles andere „A“ – nie offene Anträge, Notizen, Tage oder Konten. Andere Abteilungen sieht man wie
  `kollege`. Antwortfeld `sicht` = wirksame Sicht, `urlaubAbteilung` = Name der eigenen Abteilung (sonst `null`). Wer „U“
  von „A“ unterscheiden kann, kann Krankheitstage ableiten; deshalb kein Standardrecht.
- **`hr-einstellungen`**: `{"rev": 1, "sperren": [{"von": "…", "bis": "…", "text": "Inventur"}], "ferien": [ … ], "uebertragBis": "03-31", "antraege": true}` – `uebertragBis` (Verfallstag des Resturlaubs, Monat-Tag) ist optional; fehlt es, gilt der 31.03. `antraege` (Schalter „Urlaubsanträge über die Plattform“, Verwaltung → Urlaub, Aktion `hr_antraege_save`) ist optional; nur `false` schaltet Anträge aus, fehlt es, sind sie eingeschaltet.
  Seit 03.11.2026 zusätzlich optional: `regelSperren` (Sperren aus den Urlaubsregeln – Ostergeschäft: zwei Wochen vor
  Karfreitag, Weihnachtsgeschäft: 30.11. bis 23.12. (seit 11.11.2026; vorher ab dem Montag der letzten Novemberwoche), ohne
  Sonderregelung Dezember bis 24.12. –
  jedes Jahr berechnet, nicht gespeichert; nur `false` schaltet sie aus) und `regeln` (Text der Urlaubsregeln beim Urlaubsantrag; fehlt das Feld, gilt die Vorlage
  `HR_REGELN_STANDARD`, leer = keine Regeln; steht dort unverändert eine frühere Vorlage aus `HR_REGELN_FRUEHER`, gilt
  ebenfalls die aktuelle Vorlage – nur beim Lesen, gespeichert wird nichts). `sperren` enthält nur die eingetragenen Sperren.
  `verfallAb` (seit 03.11.2026, optional, Jahreszahl 2000–2100 oder `null`): Übergangsregel – Resturlaub verfällt erstmals am
  Verfallstag dieses Jahres; in den Jahren davor verfällt bei niemandem etwas (`hr_verfall_ab()`, `hr_konto`). Fehlt das Feld
  oder ist es `null`, verfällt Resturlaub jedes Jahr.
  `planung` (seit 03.11.2026, optional, `module/hr/planung.php`): Jahresplanung des nächsten Jahres –
  `{"start": "10-01", "stichtag": "01-31", "unverplantMax": 5, "vertretungPflicht": true, "einzeltageMax": 4, "abschluss": {"2027": {"t": "…", "by": "…", "byId": "u…"}}}`.
  Fehlende Felder gelten als Standard (Beginn 01.10., Stichtag 31.01. – seit 11.11.2026, vorher 31.12. bzw. 01.12.; ein
  gespeicherter Stichtag bleibt –, höchstens 5 Urlaubstage unverplant, Vertretung Pflicht, höchstens 4 einzelne Urlaubstage
  in der Vorplanung; `einzeltageMax` 0–50, 0 = keine Prüfung, seit 10.11.2026). `unverplantMax` (seit 11.11.2026, 0–50):
  Ziel je Mitarbeiter = Anspruch minus diese Tage (nie unter 0) – ersetzt den Anteil `prozent` (bis 11.11.2026, Standard 90 %);
  ein gespeichertes `prozent` bleibt stehen und gilt nur noch in der Vorversion. Liegt der Stichtag im Kalender vor dem
  Beginn, gilt er im geplanten Jahr selbst (`hr_planung_daten`: 01.10.2026 bis 31.01.2027 für 2027) und das laufende Jahr
  bleibt bis zum nächsten Beginn das Planungsjahr (`hr_planung_jahr`); sonst liegt der Stichtag wie bisher im Jahr davor.
  `abschluss` je Jahr setzt `hr_planung_abschluss` (Verwaltung → Urlaub speichert ihn nie mit).
  Vorplanung = Urlaub des Planungsjahres, erfasst bis zum Stichtag (`hr_vorplanung_eintrag`); Einzeltage berechnet
  `hr_einzeltage` (Blöcke über Wochenende, Feiertage, freie Tage, Gleittage und Schließtage hinweg).
  `amStueckMax` (seit 11.11.2026, optional, ganze Zahl 0–60, Standard 15, 0 = keine Prüfung): höchstens so viele Arbeitstage
  Urlaub am Stück je Antrag bzw. Vorplanung (`hr_am_stueck_block`) – Wochenenden, Feiertage, freie Tage, Schließtage und
  Gleittage verbinden, gezählt werden Arbeitstage mit Urlaub (Freitag plus ab Montag 15 Tage = 16); die Personalstelle trägt
  frei ein, die Jahresplanung zeigt längere Blöcke als Konflikt `dauer`.
  `schliesstage` (seit 10.11.2026, optional, nur `false` schaltet ab): Sonderregelung Dezember – 24.12. und 31.12. (ab 2026)
  Betrieb geschlossen, verpflichtender Betriebsurlaub: jedem Mitarbeiter im Urlaubsplan wird je ½ Tag angerechnet
  (`hr_betriebsurlaub`, gerechnet, nichts gespeichert; nicht bei K/F/X), Einträge zählen dort nicht (`hr_tag_wert` = 0), ein
  Antrag nur für diese Tage wird abgelehnt; kein „gleichzeitig weg“, Weihnachtssperre bis 23.12.
  `ueberziehenMax` (seit 10.11.2026, optional, 0–30 in halben Tagen, Standard 4): so viele Tage darf ein Urlaubsantrag bzw. eine
  Vorplanung über die verfügbaren Tage gehen – nur mit Bestätigung (`ueberziehen: true`), darüber immer abgelehnt.
  `mailVerlauf` kennt dazu die Arten `planung` und `jahresuebersicht` (mit `jahr`); E-Mails an Vertretungen stehen nur im Protokoll.
  E-Mails der Urlaubsverwaltung (`module/hr/mail.php`, optional): `mail` = `{"monat": {"an": false, "stand": "2026-10"},
  "test": {"an": false, "adresse": ""}, "steuerberater": {"an": false, "adresse": "", "tag": 5, "stand": "2026-11"}}` –
  `stand` ist der zuletzt automatisch versendete Monat (Monatsübersicht: Vormonat; Steuerberater: Versandmonat);
  `mailVerlauf` = die letzten 40 Versände `[{t, art: monat|erinnerung|steuerberater|fehlen, wie: manuell|automatisch, gesendet,
  fehler, ohneAdresse, monat, name (nur `fehlen`: Mitarbeiter), test, by}]` (ohne Inhalte).
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

- **Monatsmeldung** (`umsatz.php`, Aktion `controlling_umsatz&jahr=JJJJ`): Kg, Umsatz und DB je Monat und Vertreter eines Jahres
  (Oberfläche dazu „DB-Anteil am Umsatz“ = DB ÷ gesamter Umsatz),
  gerechnet aus `controlling-umsatzdaten` (Hauptvertreter des Kunden nach heutigen Stammdaten, „ohne Vertreter“ = `_`); DB nur mit
  `controlling.umsatz_ek` und `bestand.einkaufspreise`. Die frühere Erfassung von Hand (Dokument `controlling-umsatz`, Aktion
  `controlling_umsatz_monat_save`, Recht `controlling.umsatz_bearbeiten`) gibt es seit 01.11.2026 nicht mehr; ein vorhandenes
  Dokument bleibt auf dem Server unberührt, wird aber nicht mehr gelesen.
- **`controlling-umsatzdaten`** (vertraulich, `umsatzdaten.php`): Verzeichnis der Umsatzdaten aus der Warenwirtschaft
  `{"rev": 3, "monate": {"2026-10": {"hash": "<SHA-256>", "zeilen": 7012, "pos": 5900, "umsatz": 41234567, "menge": 3456789, "posOhne": 1800,
  "kunden": 620, "artikel": 540, "ersterTag": 1, "letzterTag": 30}}, "kunden": ["…"], "artikel": ["…"], "importe": [{"t": "…", "vonName": "…",
  "quelle": "KundenUmsatz.csv", "zeitraum": ["2022-01-03", "2026-10-30"], "neu": 1, "geaendert": 1, "entfallen": 0, "unveraendert": 56}], "geaendert": {…}}`.
  Beträge in Cent, Mengen in Tausendstel; höchstens 50 Einträge im Importverlauf.
- **`controlling-umsatzdaten/<JJJJ-MM>`** (vertraulich): `{"monat": "2026-10", "hash": "…", "zeilen": [[Tag, "Kunde", "Artikel", Kolli, Menge,
  Umsatz, EK-Wert, Umsatz mit EK, Positionen, berechnet], …]}` – je Kunde, Artikel und Tag eine Zeile, getrennt nach berechnet (mit
  Gesamtbetrag) und ohne Berechnung (z. B. Leergut; zählt nicht zu Menge und Umsatz). „Umsatz mit EK“ und EK-Wert zählen nur
  Positionen mit EK-Preis über 0 (leer oder 0 = ohne Einkaufspreis, seit 10.11.2026; ältere Monate behalten ihre Werte bis zum
  nächsten Import dieses Monats). Sortiert nach Tag, Kunde, Artikel, berechnet;
  `hash` = SHA-256 von JSON der Zeilen (gleich im Browser), Grundlage des Vergleichs beim nächsten Import.
- **`controlling-umsatzteile/<Kennung>-<JJJJ-MM>`** (vertraulich): Zwischenablage eines Imports bis zur Übernahme (mit Mitarbeiter
  und Prüfsumme); gelöscht mit der Übernahme bzw. nach einem Tag.
- **Import:** Der Zeitraum der Datei (erster bis letzter Tag) ersetzt die gespeicherten Umsätze dieses Zeitraums; Monate davor und
  danach bleiben, Randmonate behalten ihre Tage außerhalb. Verglichen wird je Monat über `hash`, übertragen werden nur neue und
  geänderte Monate – dieselbe Datei erneut ändert nichts. Die Auswertung ordnet Vertreter, Kundengruppe, Artikelgruppe und Fleischart
  nach den heutigen Stammdaten zu (die Datei enthält keine Zuordnung); die Umsatzzeilen selbst bleiben unverändert.

### Leergut (`module/leergut/leergut.php`)

Vorzeichen überall: **+ der Partner schuldet uns, − wir schulden dem Partner**; eine Bewegung zählt Abgang positiv, Zugang negativ.
Mengen sind Zuordnungen Lademittel → ganze Stückzahl (`{"e2": 40, "h1": 2}`), Nullen werden nicht gespeichert.

- **`leergut-stamm`**: `{"rev": 3, "lademittel": [{"id": "e2", "name": "E2-Kiste", "wert": 5.5, "aktiv": true}],
  "partner": [{"id": "p…", "name": "…", "art": "spedition", "mandant": "standard", "kontoNr": "", "kundenNr": "", "fristTage": 14, "email": "",
  "ansprechpartner": "", "lieferanten": "", "notiz": "", "lademittel": ["e2", "h1"], "aktiv": true, "rev": 2, "erstellt": {…}, "geaendert": {…},
  "quelle": "import|winab"?}]}`. `kundenNr` = WinAB-Kundennummer (nur Ziffern, eindeutig; ohne Angabe beim Ändern bleibt sie), `quelle: "winab"` =
  beim WinAB-Import angelegt (Kunde „Firma (Kd.-Nr.)“, Lieferant siehe unten). `lieferantNr` = WinAB-Lieferantennummer
  (Lieferanten, Speditionen; nur Ziffern), `lieferantNrWeitere` = weitere Nummern desselben Kontos (Text, durch Komma/Leerzeichen getrennt,
  höchstens 50), `winabAb` = „WinAB-Belege ab“ (Datum, leer = alle), `wareneingangTausch` (bool, Standard aus: Wareneingänge zählen nur den Zugang).
  Eine Nummer darf an mehreren Konten stehen, wenn deren `winabAb` verschieden ist (Wechsel des Kontoinhabers); neue Lieferantenkonten heißen
  „Name1 (Nr.)“ aus den Lieferanten-Stammdaten der Verwaltung (sonst „Lieferant <Nr.> (WinAB)“). Lademittel tragen `winabNr` und `kurz` (WinAB-Stammdaten). `winab` (nach einer WinAB-Datei):
  `{"ersteLieferung": "…", "letzteLieferung": "…", "letzteRueckgabe": "…", "bis": "<Stand der Datei>"}` – laut WinAB, auch aus reinem Tausch
  (Belege ohne Wirkung auf den Saldo werden nicht gebucht); spätere Berichte führen es fort (erste = früheste, letzte = späteste Angabe).
  Ohne Dokument gelten die Grundwerte `lg_grund_lademittel()` (E2 5,50 €, H1 36,00 €, übrige ohne Wert). Lademittel werden nie
  entfernt, nur deaktiviert (sonst wären Buchungen nicht mehr lesbar); neue Kennungen entstehen aus dem Namen.
- **`leergut-bewegungen`** (Historie): `{"rev": 9, "liste": [{"id": "b…", "partner": "p…", "datum": "2026-10-26", "typ": "bewegung",
  "abgang": {"e2": 63}, "zugang": {}, "beleg": "", "text": "", "quelle": "hand|import|winab", "erfasst": {"t": "…", "von": "…", "vonId": "u…"},
  "storno": null, "winab": {"kd": "9100001", "art": "Lieferschein", "beleg": "500001"} | {"lf": "2850008", "art": …, "beleg": …}?}]}`.
  `winab` (nur bei `quelle: "winab"`) ist der Schlüssel für den Abgleich mit der nächsten Datei (Kunde `kd` oder Lieferant `lf`). Nur anhängen; Stornieren setzt `storno: {t, von, vonId, grund}`, die Bewegung zählt dann nicht mehr.
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

WinAB-Datei (`leergut_winab_import`, nur mit `leergut.verwalten`, `vorschau: true` schreibt nichts): `{"bericht": {"datei": "…", "von": "<Übernehmen ab>",
"bis": "<Stand>", "dateiVon": "<Beginn der Datei>"?, "lfVon": "<Lieferantenbelege ab>"?, "quelle": "csv"?}, "kunden": [{"nr": "9100001", "name": "…"?}],
"lieferanten": [{"nr": "2850008", "lieferscheine": 12}]?, "belege": [{"kd": "9100001" | "lf": "2850008",
"art": "Lieferschein|Gutschrift|Rechnung", "beleg": "500001", "datum": "…", "abgang": {"e2": 21}, "zugang": {"e2": 20}}],
"zuordnung": {"2850008": "<Partner-ID>|neu"}?}` – `kunden`/`lieferanten` nennen alle der Datei (je Kunde optional `ersteLieferung`,
`letzteLieferung`, `letzteRueckgabe` ab `dateiVon`). Ohne Name holt der Server die Firma aus dem Kundenstamm der Verwaltung (`customers_load`,
nur lesend). Lieferantenbelege werden nur bei Partnern mit `lieferantNr` gebucht; `zuordnung` setzt die Nummer an einem bestehenden Partner
(kein Kundenkonto, noch ohne Nummer) oder legt ein Konto an. Abgleich je Kunde bzw. Lieferant, Belegart und Belegnr. nur im Zeitraum und für die
Genannten; geänderte Belege werden storniert und neu gebucht, fehlende storniert (Grund „WinAB-Abgleich vom …“). Antwort zusätzlich
`lieferanten` (Nr., Name und Versandart aus den Lieferanten-Stammdaten, Belege mit Wirkung, Saldo ohne Konto, zugeordneter Partner, `vorschlag` =
Konto ohne Nummer mit passendem Namen) und `summeLieferanten`; `zaehler` nennt `tausch` (Wareneingänge mit nicht gezähltem Tausch) und `vorStart`
(Belege vor „WinAB-Belege ab“). `leergut_start` liefert dazu `versand` (Versandart je Partner) und `winabBestand` (je Partner `[[WinAB-Nr., Stück], …]` aus
`lademittelbestand` des Lieferanten- bzw. Kundenstamms – nur Anzeige, `lg_partner_stamm`). Beginn je Konto (`lg_winab_beginn`): `winabAb`, sonst Tag nach der letzten Buchung mit `quelle: "import"` (Excel-Liste, `lg_excel_index`), sonst `von`;
gebuchte WinAB-Belege davor werden storniert (`zaehler.vorBeginnStorniert`; bei `von` nur mit `bericht.aeltereStornieren`). Liegt `winabAb` vor dem Ende
der Excel-Liste, werden WinAB-Belege dort nur gebucht, wenn sie fehlen (`lg_excel_passt`: gleiche Wirkung ±3 Tage = schon da, gleicher Tag und Richtung
mit anderer Menge = abweichend, beides nicht gebucht; früher gebuchte storniert). `zaehler` dazu: `inExcel`, `abweichend`, `nurWinab`, `doppeltStorniert`; Antwort `abweichend`
(je Beleg Konto, Datum, Beleg, Wirkung laut WinAB und laut Excel, Excel-Beleg). `lfVon` (die Seite schickt `dateiVon`, also alle Lieferantenbelege der Datei) gilt für Lieferantenbelege; die Seite setzt es auf das früheste
`winabAb` der Konten. Wareneingang = Lieferschein eines Lieferanten: gebucht wird der Zugang, als Abgang nur `max(0, Abgang − Zugang)`
(außer `wareneingangTausch`). Zeilen mit Kunde sind Kundenbelege,
auch wenn WinAB dort zusätzlich eine Lieferantennummer nennt (die zählt dort nicht). Die Datei bleibt im Browser;
gespeichert werden nur die Buchungen.

### REWE (`module/rewe/rewe.php`, in Prüfung)

Kalenderwochen sind ISO-Wochen „JJJJ-WW“ und meinen die **Lieferwoche**. Mengen sind Zuordnungen Artikel → ganze Stückzahl
(`{"rb": 2, "fk": 1}`, 1 Stück = 1 Kolli). Alle Schreibvorgänge laufen unter der Sperre `rewe-maerkte`.

- **`rewe-stamm`**: `{"rev": 2, "lieferwege": [{"id": "l…|direkt", "name": "…", "art": "lager|direkt", "bestellschluss": "Freitag früh der Vorwoche",
  "aktiv": true}], "artikel": [{"id": "rb", "name": "Roastbeef Dry Aged", "einheit": "Stück", "nr": "<WinAB-Artikelnummer>", "aktiv": true}],
  "team": {"u…": {"alle": true, "export": false}}, "mitglieder": ["u…"], "ausgeblendet": ["u…"]}`. Ohne Dokument gelten Direktbelieferung
  und die Artikel Roastbeef, Filetkopf, Vac. Set. Lieferwege und Artikel werden nie entfernt, nur deaktiviert. `team` ist die Zuweisung
  im Modul („alle Listen“, „Wochenabschluss“) und wirkt zusätzlich zu den Rechten `rewe.alle` und `rewe.exportieren`.
  `mitglieder` und `ausgeblendet` (seit 11.11.2026, fehlen = leere Listen) sind das Team der Zuweisung: wer im Team ist, entscheidet nur
  `rw_im_team()` – aktiv, mit Zugang, nicht in `ausgeblendet` und entweder „REWE ansehen“ über die Rollen oder in `mitglieder`
  (ausdrücklich ergänzt, mit Modulzugang `rewe.zugang`, ohne Verbot am Konto). Ergänzte sehen, fragen ab und pflegen ihre eigenen
  Märkte wie mit `rewe.sehen` + `rewe.bearbeiten` (`rw_sehen()`, `rw_bearbeiten()`; die Aktionen prüfen mit `rw_require_perm('rewe.sehen'|'rewe.bearbeiten')` statt `require_perm`).
  `rewe_team_ergaenzen` nimmt die ID aus `ausgeblendet` und – ohne Rollenrecht – in `mitglieder` auf; `rewe_team_entfernen`
  (nur ohne Märkte ab der Abfragewoche, sonst 422) nimmt sie aus `mitglieder` und `team` und setzt sie auf `ausgeblendet`.
  Rollenrechte, frühere Zuständigkeiten und Schnappschüsse bleiben. Die Vorversion ignoriert beide Felder (Ergänzte ohne Recht
  sehen dann nichts); Team speichern, Lieferwege/Artikel und das Datenpaket („ersetzen“) behalten sie.
- **`rewe-maerkte`**: `{"rev": 5, "liste": [{"id": "m…", "rev": 3, "kdNr": "<WinAB-Kd.-Nr.>", "reweNr": "", "name": "…", "strasse": "", "plz": "",
  "ort": "…", "region": "", "telefon": "", "kauf": "regelmaessig|gelegentlich|interessiert|kein_interesse|ruhend|ausgelistet",
  "zustaendig": [{"ab": "2026-01", "nutzer": "u…|"}], "lieferweg": [{"ab": "2026-01", "id": "l…"}], "dauer": {"rhythmus": 0-4,
  "mengen": {…}, "ab": "JJJJ-WW", "pauseBis": ""}, "abfragetag": "mo…fr|", "ansprechpartner": [{"name": "…", "rolle": "", "telefon": "",
  "email": ""}], "hinweis": "", "erstellt": {…}, "geaendert": {…}}]}`. `zustaendig` und `lieferweg` sind „ab KW“-Historien (gilt der
  letzte Eintrag mit `ab` ≤ KW). Steht die Kd.-Nr. im Kundenstamm der Verwaltung, kommen Name, Anschrift und Telefon von dort.
  `hinweis` bis 4.000 Zeichen (seit 03.11.2026, vorher 1.000; mehrzeilig).
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
Nutzer-ID, nur Mitarbeiter im Team). Mit Fehlern wird nichts übernommen, in ein Modul mit Daten nur mit `ersetzen` (das Team mit
`team`, `mitglieder` und `ausgeblendet` bleibt). Echte Pakete liegen nie
im Repository (GR-007); Beispiel: `tests/fixtures/rewe/datenpaket.json`.

### Qualitätssicherung · QM-System (`module/qs/qs.php`, produktiv seit 30.10.2026)

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
  **Vorlagen und Lenkungsangaben** (seit Bauabschnitt 3, `module/qs/vorlagen.php`): Datei-Einträge optional mit `platzhalter: ["version", …]`
  (bekannte, noch offene Platzhalter in Word/Excel), `vorlage: {"dokument", "nr", "version"}` (aus einer Vorlage erzeugt), `uebernommen: N`
  (Kopie aus Version N), `roh: "<id>"`, `sha256Roh` (Prüfsumme der Rohfassung) und `ausgefuellt: {"t", "felder"}` (bei der Freigabe bzw. beim Nachtragen ausgefüllte Fassung; `roh` ist
  die Rohfassung mit Platzhaltern, sie bleibt in der Ablage und wird bei „Dateien übernehmen“ kopiert). Vorlagen (Art V) werden nie ausgefüllt.
  **Nummernstruktur:** Arten A, F, L, E heißen `<Kapitel>-<Art><2–3 Ziffern>`; beim Anlegen und bei Änderung von Nummer, Kapitel oder Art
  prüft `qs_dokument_save` sie (leer = nächste freie, höchste vorhandene + 1 – auch eingezogene zählen); das Datenpaket prüft sie nicht.
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

Audit-Bericht (`qs_bericht`, `qs_bericht_excel`, GET `von`/`bis`, höchstens zwei Jahre, endet spätestens heute; `module/qs/bericht.php`)
liest nur: Kalender-Intervalle je Periode wie die Fälligkeit (gezählt im Monat des Periodenendes; eine Periode zählt, wenn sie zum
Stichtag `bis` vorbei ist oder schon einen Nachweis hat; Nachweise nach dem Stichtag zählen nicht), längere Intervalle als Fristenkette
(`eingehalten|verspaetet|ueberfaellig|offen|nie`), Abweichungen mit Maßnahme, Maßnahmen (bis zum Stichtag erfasst, im Zeitraum offen oder
abgeschlossen; Status Stand heute), Freigaben/Überprüfungen/Einziehungen und Handbuch-Änderungen im Zeitraum. Excel ohne Formeln.

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
| Controlling | `vertreter_load()`, `gruppen_load()` (Kundengruppen, VK-Gruppen), `customers_load()` (Firma, Ort, Vertreter, Kundengruppe), Artikelstammdaten (Name, VK-Gruppe, Fleischart) – nur lesend für Umsatzstatistik und Umsatzauswertung | Verwaltung |
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
