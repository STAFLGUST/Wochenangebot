# ADR-007: Kundenseite in eigenem Container

**Status:** angenommen am 04.11.2026 (Inhaber). **Stufe 1** umgesetzt und eingespielt (PR #281), **Stufe 1b**
(Dienstkonto in Keycloak, Realm Stand 16) umgesetzt und eingespielt (PR #283), **Notzugang über einen SSH-Tunnel**
(Regel 6 der Zielarchitektur Kundenseite) umgesetzt und eingespielt (PR #285); **Postausgang von innen** (Regel 4)
umgesetzt und eingespielt (PR #286, Schlüssel umgezogen am 04.11.2026); **Stufe 2a** (interne Daten in eigenen Ordner)
umgesetzt und eingespielt (PR #287, Daten getrennt am 04.11.2026); **Stufe 2b** (Trennstufe 2: Kundendokument geteilt, Bestand,
Stammdaten, Postfächer und Empfänger innen, Postausgang prüft Versandaufträge) umgesetzt – wirksam erst mit dem Serverschritt
`deploy/daten-trennen.sh trennen` nach dem Release (Freigabe des Inhabers); **Stufe 2c** (Trennstufe 3: Veröffentlichtes
maßgeblich innen, Kundenseite nur eine nicht beschreibbare Kopie), **Stufe 2d** (Trennstufe 4: Protokoll getrennt) und **Stufe 2e**
(Trennstufe 5: Anmeldeversuche, Zähler und Live-Verkehr je Seite) umgesetzt – ebenfalls erst mit `trennen`.
**Härtung des Kundencontainers** (Auftrag des Inhabers 06.11.2026: „maximal gehärtet“) umgesetzt – wirksam mit dem Release,
ohne Konsolenschritt (Abschnitt „Härtung des Kundencontainers“).
**Anlass:** Sicherheitsdurchsicht vom 26.10.2026, Befund 5, und Durchsicht aus Kundensicht vom 04.11.2026 (ohne Befund,
aber mit diesem Restrisiko). Umsetzung der Vorgabe aus [ADR-003](adr-003-domains-anmeldung.md): Trennung
Kunden/Mitarbeiter; eine kompromittierte Anwendung darf nicht automatisch andere Fachbereiche öffnen.

Ergänzt die [Zielarchitektur](zielarchitektur.md) §1 und §3: Der Code bleibt ein modularer Monolith (ein Image, ein
API-Einstieg, gemeinsame Dienste). Getrennt wird nur der **Betrieb**: Die öffentliche Seite bekommt ihren eigenen Container.

## Ausgangslage

Bisher beantwortete ein Container `app` die öffentliche Seite `angebot-stafl.de`, die jeder ohne Anmeldung aufrufen kann,
**und** alle Mitarbeiter-Hosts. Der Name `app-mitarbeiter` war nur ein zweiter Netzwerkname desselben Containers. Darin
lagen gleichzeitig:

- alle Geheimnisse der Mitarbeiteranmeldung (je Host ein Keycloak-Client),
- das Dienstkonto `konten` (Keycloak-Rollen `view-users`, `manage-users`: Mitarbeiterkonten anlegen, Passwörter setzen),
- der Zugang zum Postfach,
- der vollständige Datenordner (Personal, Nutzer, Kunden mit Warenwirtschaftszahlen, Protokolle),
- eine Netzverbindung zu Keycloak.

Die Trennung im Code (GR-003, GR-104, GR-109) hält – die Durchsicht vom 04.11.2026 fand keine Lücke. Gäbe es aber
einmal eine Lücke, die Code im Prozess der öffentlichen Seite ausführt (zum Beispiel in einer künftigen PHP-Version), stünde
der Angreifer neben allem anderen.

## Entscheidung

### Stufe 1 – Prozesse, Geheimnisse und Netze trennen (umgesetzt)

| | `app` (Kundenseite) | `app-mitarbeiter` (Mitarbeiter-Hosts) |
| --- | --- | --- |
| Hosts | `angebot-stafl.de` | `dashboard-stafl.de`, `*.dashboard-stafl.de`, Prüfung vor der Anmeldeseite |
| Image und Code | `stafl-app` (baut dieser Dienst) | dasselbe Image, nie aus dem Netz geholt |
| Apache | nur Standard-Host, `mod_auth_openidc` nicht geladen | zusätzlich `apache-oidc.conf` (Keycloak-Hosts) |
| Geheimnisse | Postfach (für Bestellwünsche und Passwort-Links) | alle Anmelde-Geheimnisse, Dienstkonto `konten`, Postfach |
| Netz | `default` – nur mit Caddy | `intern` – mit Caddy und Keycloak |
| Dateisystem | nur lesbar; `/tmp` und `/run` im Speicher | wie bisher |
| Grenzen | `no-new-privileges`; CPU, Speicher, Prozesse (über `.env` anpassbar) | keine |
| Datenordner | gemeinsam (Stufe 1) | gemeinsam |

- Konfiguration: `deploy/anmeldung/docker-compose.anmeldung.yml` (aktiv über `COMPOSE_FILE` in `.env`). Ohne
  Ergänzungsdatei bleibt es bei einem Container wie bisher (lokale Entwicklung).
- Caddy bleibt unverändert: `angebot-stafl.de` → `app`, alle Mitarbeiter-Hosts → `app-mitarbeiter`. Caddy hängt zusätzlich
  im Netz `intern`; Keycloak hängt nur noch in `intern` und `anmeldung`.
- Der Server weist Mitarbeiter-Aktionen auf der Kundenseite schon heute ab (alter Eingabebereich stillgelegt, 410). Im
  eigenen Container fehlen dort zusätzlich die Keycloak-Hosts, die Geheimnisse und der Netzweg.
- **Notzugang** (`deploy/notzugang.sh`, Keycloak gestört): bis 04.11.2026 auf `angebot-stafl.de/admin/` im Container `app`,
  seitdem nur noch über einen SSH-Tunnel (Abschnitt „Notzugang über einen SSH-Tunnel“ unten). Die Kundenseite öffnet den
  alten Eingabebereich nie mehr. Konten der zentralen Anmeldung lassen sich im Notzugang nicht verwalten – im Notfall ist
  Keycloak ohnehin gestört.
- Geprüft in der CI: `deploy/anmeldung/pruefen.sh` (Konfiguration und echter Start beider Container: Netze, Umgebung,
  nur lesbares Dateisystem, Grenzen), `tests/deploy/test_freigabe.sh` (Release), `tests/deploy/test_datenbank_umschalten.sh`.

### Stufe 1b – Dienstkonto in Keycloak beschneiden (umgesetzt 04.11.2026, Realm Stand 16)

Stufe 1 nimmt das Dienstkonto aus dem öffentlich erreichbaren Prozess und aus dessen Netz. In Keycloak selbst hatte es bis
dahin `manage-users` für **alle** Konten des Realms `mitarbeiter` – wer sein Geheimnis erbeutete, konnte das Passwort jedes
Administrators setzen. Seit Stand 16 gilt:

- **Lesen** darf der Client `konten` alle Konten (`view-users`), damit die Verwaltung Zustand und Administratoren erkennt.
- **Ändern und anlegen** nur Konten der Gruppe `anwendungskonten` – feingranulare Verwaltungsrechte von Keycloak
  (Version 2, ab Keycloak 26.2): eine Regel „Dienstkonto der Anwendung (Client konten)“ und eine Berechtigung auf die Gruppe
  mit `view-members`, `manage-members`, `manage-membership`. Neue Konten legt der Client nur in dieser Gruppe an. Jemanden in
  die Gruppe aufnehmen oder daraus entfernen, Rollen vergeben oder sich als jemand anderes anmelden kann er nicht (geprüft
  mit echtem Keycloak 26.8.1, `tests/oidc/test_oidc.py`).
- **In der Gruppe** stehen genau die Konten der Mitarbeiter ohne Administratorrolle (verknüpft oder gleicher Benutzername) –
  nie Administratoren, nie Konten mit Verwaltungsrollen von Keycloak, nie Service-Accounts, nie Konten gelöschter Mitarbeiter.
  Den Abgleich macht nur die Serverkonsole: `sh deploy/anmeldung/konten.sh gruppe-abgleichen` (auch in
  `realm-aktualisieren`; `anlegen` und `einladen` nehmen neue Konten von Nicht-Administratoren gleich auf).
- **Die Anwendung** ändert Konten von Administratoren selbst dann nicht, wenn Keycloak es noch zuließe, legt für
  Administratoren keine Konten an und nennt in der Verwaltung stattdessen den Befehl der Serverkonsole.
- **Anmeldung:** Ein Administrator meldet sich nie mit einem Konto der Gruppe an (`lib/oidc.php`,
  `oidc_admin_konto_pruefen`). Sonst könnte, wer das Geheimnis hat, ein Konto mit dem Benutzernamen eines noch nicht
  verknüpften Administrators anlegen (die erste Anmeldung verknüpft über den Benutzernamen) oder das Passwort eines frisch
  beförderten Administrators setzen.
- **Folgen im Alltag:** Wird jemand Administrator (oder nicht mehr), danach `konten.sh gruppe-abgleichen <name>` – bis dahin
  meldet sich ein frisch beförderter Administrator nicht an, und die Verwaltung warnt. Passwort, Sperre und Einladung von
  Administratoren nur noch in der Konsole (`startpasswort`, `entsperren`, `einladen`). Der Notfallmodus meldet die
  Keycloak-Sitzungen anderer Administratoren nicht mehr ab (die Anwendung verlangt von ihnen trotzdem eine erneute Anmeldung).
  Alte Konten gelöschter Mitarbeiter außerhalb der Gruppe löscht nur `konten.sh verwaist --loeschen`.
- **Einführung:** nach Merge und Release einmal `sh deploy/anmeldung/konten.sh realm-aktualisieren` (Freigabe Inhaber). Die
  Reihenfolge darin schließt jede Lücke aus: erst Gruppe und Berechtigung, dann Abgleich, zuletzt `manage-users` entfernen.
  Neuer Code vor dem Konsolenschritt arbeitet wie bisher (ohne Gruppe keine Gruppenangabe beim Anlegen).
- **Rückweg:** `kc add-roles … manage-users` für den Service-Account von `konten` gibt den alten Zustand zurück
  (`docs/plattform/inbetriebnahme-anmeldung.md`); Gruppe, Regel und Berechtigung stören dann nicht.

### Notzugang über einen SSH-Tunnel (umgesetzt 04.11.2026)

Der alte Eingabebereich mit eigener Anmeldung ist der Notzugang, wenn Keycloak gestört ist. Bis dahin lag er auf der
Kundenseite: `notzugang.sh an` öffnete `angebot-stafl.de/admin/` im öffentlich erreichbaren Container `app` – für alle im
Internet, mit den alten Passwörtern. Seitdem:

- **Eigener Host im Container `app-mitarbeiter`:** Apache-Port 8090 (`deploy/anmeldung/apache-oidc.conf`), von Docker nur
  auf `127.0.0.1:${NOTZUGANG_PORT:-8190}` des Servers veröffentlicht – Caddy kennt ihn nicht. Erreichbar nur über einen
  SSH-Tunnel vom eigenen Rechner (`ssh -L 8190:127.0.0.1:8190 <benutzer>@<server>`, dann `http://localhost:8190/admin/`),
  wie die Keycloak-Verwaltung auf `127.0.0.1:8180`.
- **Offen nur mit `WA_NOTZUGANG=an`** in `.env` (`sh deploy/notzugang.sh an`, erstellt nur `app-mitarbeiter` neu);
  sonst antwortet der Host wie `angebot-stafl.de` (Mitarbeiteraktionen 410). `WA_EIGENE_ANMELDUNG` steht in beiden
  Anwendungs-Containern fest auf `aus`; eine frühere Zeile `WA_EIGENE_ANMELDUNG=an` in `.env` öffnet nichts mehr und
  entfernt `notzugang.sh` beim Umschalten.
- **Erkennung in der Anwendung:** `notzugang_host()` (`lib/oidc.php`) – der Webserver setzt `WA_NOTZUGANG_HOST` (nie aus
  Kopfzeilen), die Anfrage kommt direkt von einer internen Adresse (Docker-Netz des Tunnels) und ohne weitergereichte
  Besucheradresse. Nur dort gilt die **IP-Freigabe** des Eingabebereichs nicht: Die Besucheradresse ist die interne Adresse
  des Tunnels und stünde nie in der Liste; hinkommt ohnehin nur, wer sich am Server anmelden kann.
- **Nur http über den Tunnel:** Der Host nimmt `upgrade-insecure-requests` aus der Inhaltsrichtlinie (`.htaccess`), sonst
  holte der Browser Skripte über https; `localhost` gilt im Browser als sichere Umgebung (Cookies, Einmalcode).
  Passkeys der alten Anmeldung gehören zu `angebot-stafl.de` und gelten im Notzugang nicht – Passwort und Einmalcode schon.
- **Geprüft:** `tests/deploy/test_notzugang.sh` (Skript), `deploy/anmeldung/pruefen.sh` (echter Start: Port nur auf
  127.0.0.1, geschlossen/offen, Kundenseite bleibt zu, Kopfzeilen), `tests/oidc/test_oidc.py` (Anmeldung im Browser über
  http, keine Skriptfehler, IP-Freigabe-Ausnahme nur für diesen Host).
- **Rückfall:** Ein Release auf den Vorgänger stellt den alten Notzugang auf der Kundenseite wieder her (dann gilt wieder
  `WA_EIGENE_ANMELDUNG` in `.env`); `WA_NOTZUGANG` und `NOTZUGANG_PORT` werden dann ignoriert.

### Postausgang von innen (umgesetzt 04.11.2026)

Regel 4 der Zielarchitektur Kundenseite, vorgezogen aus Stufe 2: Die Kundenseite verschickt keine E-Mails mehr und kennt
kein Postfach.

- **Kundenseite legt nur ab:** Mit `WA_POSTAUSGANG=warteschlange` (nur im Container `app`) speichert ein Bestellwunsch seine
  Versandaufträge wie bisher beim Vorgang und legt zusätzlich einen Auftrag mit der Bestellnummer im Dokument `postausgang` ab
  – im selben Speichervorgang. Ebenso Benachrichtigungen, die eine Kundenaktion auslöst (z. B. Anmeldesperre nach
  Fehlversuchen), und der Hinweis an das Team bei Ab- oder Wiederanmeldung vom Wochenangebot. Die Quittung meldet
  `delivery: "eingegangen"` und kündigt die Kopie an (`copyPlanned`); ein Postfachausfall führt nicht mehr zu 502.
- **Dienst `postausgang`** (`app/api/postausgang.php`, `lib/postausgang.php`): gleiches Image, als `www-data`, Dateisystem
  nur lesbar, kein Port, eigenes Netz nur mit Ausgang ins Internet (SMTP). Ein Durchgang alle 5 Sekunden, jeder als eigener
  Prozess (hält keine Sperre der Speicherschicht dauerhaft). Er verschickt fällige Aufträge, prüft alle 10 Minuten alle
  Vorgänge auf liegengebliebene Versandaufträge und schreibt ein Lebenszeichen (`postausgang-stand`).
- **Wiederholung nur ohne Doppelversand-Risiko:** Ist das Postfach gestört, versucht der Dienst es nach 1, 5 und 30 Minuten
  erneut – aber nur, wenn die Mail nachweislich nicht angekommen ist (keine Verbindung, Anmeldung, Ablehnung, Notfallmodus).
  Unklare Fälle und alles danach bleiben wie bisher in den Bestellwünschen zum bestätigten Nachsenden stehen.
- **Bestellfunktion ehrlich:** Die Kundenseite kann das Postfach nicht selbst prüfen. Sie nimmt Bestellwünsche nur an, wenn
  der Dienst ein eingerichtetes Postfach meldet und sich in den letzten 15 Minuten gemeldet hat – sonst bleiben sie nicht
  unbemerkt liegen.
- **Schlüssel des hinterlegten Postfach-Passworts** außerhalb des gemeinsamen Datenordners: `WA_GEHEIM_DIR`
  (`./daten-geheim`, nur in `app-mitarbeiter` und `postausgang` eingebunden, wie bisher nicht gesichert). Die Kundenseite
  sieht nur das verschlüsselte Passwort. Die `MAIL_*`-Werte aus `.env` sind in `app` geleert.
- **Passwort an das Postfach gebunden** (Format v2, AEAD mit Server, Port, Verschlüsselung und Benutzer als zusätzlichen
  Daten): Wer im gemeinsamen Datenordner einen fremden Server einträgt, bringt den Postausgang nicht dazu, sich dort mit dem
  echten Passwort anzumelden – die Entschlüsselung schlägt fehl. Gebunden wird nur, solange der Schlüssel in `daten-geheim`
  liegt; Format v1 bleibt lesbar.
- **Einführung (Serverschritt nach dem Release):** `sh deploy/postfach-schluessel.sh umziehen` – verschiebt den Schlüssel
  (ohne Neustart; bis dahin gilt der bisherige Ort) und bindet vorhandene Passwörter (v1 → v2) im Dienst `postausgang`.
- **Grenze bis Stufe 2b:** Solange Empfänger und Inhalt im gemeinsamen Ordner standen, konnte eine übernommene Kundenseite
  gefälschte Versandaufträge ablegen, die der Postausgang verschickte. Das Passwort selbst bekam sie nicht mehr. Geschlossen mit
  Trennstufe 2 (Abschnitt Stufe 2b).
- **Geprüft:** E2E-Gruppe `postausgang` (zwei Server wie im Betrieb: Kundenseite ohne Postfach, Mitarbeiterseite mit
  Schlüsselordner; Dienst wie im Container; Oberfläche Desktop und 390 px), `tests/deploy/test_postfach_schluessel.sh`,
  `deploy/anmeldung/pruefen.sh` (Konfiguration und echter Start: Dienst läuft, abgeschottet, Kundenseite ohne Postfach).
- **Rückfall:** Vor einem Release-Rückfall `sh deploy/postfach-schluessel.sh zurueck` – stellt die Passwörter auf Format v1
  zurück und legt den Schlüssel wieder in den Datenordner (ältere Stände kennen nur das; sonst müsste das Postfach-Passwort
  nach dem Rückfall neu eingegeben werden). Danach bleibt der Container `postausgang` verwaist stehen (`docker compose up -d --remove-orphans`);
  Aufträge im Dokument `postausgang` verarbeitet der alte Stand nicht – offene Versandaufträge stehen weiter beim Vorgang und
  lassen sich in den Bestellwünschen nachsenden.

### Stufe 2a – Interne Daten in einen eigenen Ordner (umgesetzt und getrennt am 04.11.2026, Trennstufe 1)

Gemessen (Zugriffsspur der Speicherschicht über 24 Testgruppen, 04.11.2026): Die öffentlichen Kundenaktionen fassen 38
Speicherdokumente an. Alle übrigen – Personal (HR), Mitarbeiterkonten und Sitzungen, Rechte, CRM, Controlling, Marketing,
Leergut, REWE, QS mit der Dateiablage, Entwurf, Versionen, Preisverlauf, Einkauf, Versandprotokoll … – braucht die Kundenseite nie.

- **Einteilung im Regelwerk:** jedes Dokument in `regeln/datenverantwortung.toml` hat `bereich = "kundenseite"` oder
  `"intern"` (Pflicht, CI). Daraus entsteht `app/api/lib/datenbereiche-liste.php`. Neue Dokumente sind intern, außer die
  Kundenseite braucht sie nachweislich (Testgruppe `datentrennung`).
- **Speicherschicht mit zwei Bereichen** (`app/api/storage.php`): Nach dem Trennen (Kennzeichen `daten/.daten-getrennt`)
  liegen interne Dokumente im Ordner `WA_DATEN_INTERN` (Kennzeichen `.daten-intern`), mit eigenen Sperren und im
  SQLite-Betrieb eigener Datenbank; die Dateiablage `dateien/` ebenso. Nur `app-mitarbeiter` und `postausgang` binden
  `./daten-intern` ein (außerhalb der Webwurzel). Die Kundenseite liest interne Dokumente nicht (null), schreiben bricht ab.
  Ohne Kennzeichen ist alles wie bisher – das Release allein ändert nichts.
- **Maßgeblich ist das Kennzeichen innen** (seit 05.11.2026): `daten/.daten-getrennt` liegt im Ordner, den die Kundenseite
  beschreiben kann – ein herabgesetztes oder entferntes Kennzeichen hätte interne Dokumente (Bestand, Protokoll, Postfach …)
  wieder dem gemeinsamen Ordner zugeordnet. Server mit `WA_DATEN_INTERN` (Mitarbeiterseite, Postausgang) nehmen die Stufe
  deshalb aus `daten-intern/.daten-intern` und brechen ab, wenn das gemeinsame Kennzeichen eine niedrigere Stufe nennt, fehlt
  oder eine andere Speicherart meldet (`.sqlite-active`) – nie still falsch lesen oder schreiben. Die Kundenseite liest weiter
  das gemeinsame Kennzeichen; dort gewinnt eine Herabsetzung nichts, weil sie den internen Ordner nicht sieht.
  `daten-trennen.sh` arbeitet mit gestoppter Anwendung, die Prüfung greift also nur im laufenden Betrieb.
- **Serverschritt** `sh deploy/daten-trennen.sh trennen` (im Wartungsfenster, Freigabe des Inhabers): Sicherung → Stopp von
  `app`, `app-mitarbeiter`, `postausgang` → `deploy/daten_trennen.py` (kopieren und vergleichen, dann umschalten, dann
  Originale entfernen; ein Abbruch vor dem Umschalten lässt alles wie vorher) → Eigentümer → Start. `status` zeigt den Plan,
  ohne etwas zu ändern. Dateien und SQLite werden beide unterstützt.
- **Altbestand des Speicher-Umbaus** (seit 05.11.2026): Der Umstieg auf SQLite lässt die bisherigen Datendateien absichtlich
  liegen, ein Rückfall die inaktive Datenbank. `status` nennt diese Reste („Reste des Speicher-Umbaus im gemeinsamen Ordner“);
  `trennen` bricht ab, solange eine inaktive `daten/.sqlite` dort liegt (erst archivieren, `docs/datenbank.md`), und entfernt
  die Altdateien der gekürzten Dokumente `kunden` und `bestellung` – sonst stünden Anschriften, Warenwirtschaftsdaten und die
  Empfängeradressen weiter im Ordner der Kundenseite. Gelesen werden die Altdateien nie; ein Rückfall auf Dateien schreibt sie
  aus der Datenbank neu (`datenbank.py rollback`).
- **Zwischendateien der Serverskripte** (seit 05.11.2026): `daten/` und `daten-geheim/` sind in den Containern beschreibbar.
  Skripte, die als root dort hineinschreiben, legen die Datei außerhalb an und bringen sie nur per Umbenennen hinein
  (`mv -fT`, `os.replace`) bzw. öffnen sie mit `O_NOFOLLOW` – ein dort vorab angelegter Verweis lenkt so nichts um
  (`deploy/postfach-schluessel.sh`, `deploy/daten_trennen.py`, `deploy/datenbank.py`; Vorbild `deploy/sichern.sh`).
- **Sicherung:** `deploy/sichern.sh` sichert danach zusätzlich `daten-intern/` als `intern-<Zeit>.tar.gz` (gleich geprüft) und
  bricht ab, wenn der Ordner fehlt. Ob gesichert wird, entscheidet seit 05.11.2026 das Kennzeichen `daten-intern/.daten-intern`
  (nicht mehr allein das gemeinsame): ein entferntes Kennzeichen in `daten/` kann die internen Daten nicht still aus der
  Sicherung nehmen; fehlt eines der beiden, bricht die Sicherung mit Fehler ab. Dabei behoben: Im SQLite-Betrieb fehlte die Dateiablage (hochgeladene QS-Dokumente) in der
  Sicherung – der Datenbankabzug nimmt sie jetzt mit.
- **Speicher umschalten / Altdateien** (`datenbank-umschalten.sh`, `altdateien.sh`) laufen nur mit allen Daten in einem
  Ordner: erst `daten-trennen.sh zusammenfuehren`, dann umschalten, dann wieder trennen.
- **Rückfall:** Vor einem Rückfall auf ein Release vor der Trennung `sh deploy/daten-trennen.sh zusammenfuehren` (ältere
  Stände kennen `daten-intern` nicht). Rückfall auf ein Release *mit* Trennung: nichts zu tun.
- **Geprüft:** `tests/deploy/test_daten_trennen.py` (Dateien und SQLite: trennen, Wiederholung nach Abbruch, Schutz vor
  Überschreiben, zusammenführen ohne Verlust, gleiche Einteilung in PHP und Python, Speicherschicht beider Seiten),
  `tests/deploy/test_daten_trennen.sh`, `tests/deploy/test_sichern.sh`, E2E-Gruppe `datentrennung` (Kundenseite ohne internen
  Ordner wie im Betrieb: alle Kundenfunktionen, keine einzige Anfrage nach internen Dokumenten, Protokoll wird weiter
  geschrieben, keine Mitarbeiteranmeldung oder Ersteinrichtung), volle E2E-Suite einmal lokal mit getrennten Daten
  (`WA_TEST_TRENNUNG=1`), `deploy/anmeldung/pruefen.sh` (Einbindung).

### Stufe 2b – Trennstufe 2: weniger Daten außen, Postausgang vertraut der Kundenseite nicht mehr (umgesetzt, Serverschritt mit Freigabe)

Nach Stufe 2a sah die Kundenseite noch Dokumente, die mehr enthielten als nötig, und der Postausgang vertraute Empfängern und
Inhalt im gemeinsamen Ordner. Seit Stufe 2b gilt: **Was die Kundenseite schreiben kann, entscheidet nie, wohin oder was die Firma
verschickt, und enthält keine Daten, die sie nicht braucht.**

- **Trennstufen:** Das Kennzeichen `daten/.daten-getrennt` enthält die Stufe (1 = Stufe 2a, 2 = Stufe 2b; `store_stufe()`).
  Dokumente mit `trennstufe = 2` in `regeln/datenverantwortung.toml` liegen bis zu dieser Stufe im gemeinsamen Ordner – so ändert
  das Release allein nichts. `deploy/daten-trennen.sh trennen` bringt die Daten auf die höchste Stufe des eingespielten Stands (auch
  von Stufe 1 auf 2); `status` zeigt den Plan. Kennt ein Stand die Stufe im Kennzeichen nicht (Rückfall ohne Zusammenführen), bricht
  die Speicherschicht ab, statt still falsch zu lesen.
- **Ab Trennstufe 2 innen:** Bestand und Stammdaten (Mengen, Partien, MHD, Einkaufspreise), beide Postfach-Zugänge, die
  Signatur (`mailvorlage`), die Benachrichtigungen und die Empfänger der Bestellwünsche (`bestellung-empfaenger`; außen steht nur
  ihre Anzahl). Neu: `kundenstamm` (intern).
- **Kundendokument geteilt:** In `kunden` bleiben je Kunde nur die Portalfelder (`felder_kundenseite`: Kennung, Nummer, Firma,
  Ansprechpartner, Gruppe, Angebote, aktiv, Zugang, Wochenangebot an/ab, gekürzte E-Mail für die Abmeldeseite). Anschrift, E-Mail,
  Telefon, Notiz, Vertreter und die Daten der Warenwirtschaft (Umsätze, Kreditlimit) stehen in `kundenstamm`. Die Mitarbeiterseite
  liest beide zusammengeführt (`customers_load`) und speichert geteilt (`customers_save`) – alle Module (CRM, Controlling, REWE …)
  sehen dieselben Felder wie bisher. Die Kundenseite liest und schreibt nur die Portalfelder.
- **Auszug für die Kundenseite:** `artikelauszug` – Artikelnummern mit Lagerbestand (ohne Mengen) und Fleischart, Herkunft,
  Zustand je Artikel. Neu geschrieben nach jeder Änderung von Bestand oder Stammdaten; der Postausgang prüft ihn bei jedem Durchgang.
- **Postausgang prüft Versandaufträge** (`order_outbox.php`, `lib/postausgang.php`): Die Kundenseite legt für einen Bestellwunsch
  nur einen offenen Auftrag ohne Empfänger an; der Postausgang bestimmt die Empfänger (Bestellfunktion, Adresse aus `kundenstamm`),
  ergänzt den Schnappschuss des Kunden einmalig aus den Stammdaten (GR-106) und erzeugt den Inhalt beim Versand selbst. An das Team
  gehen E-Mails nur an heutige oder frühere Empfänger (so bleibt beim Nachsenden der Originalempfänger), die Kopie nur an die
  heutige Adresse des Kunden und automatisch nur bei eingeschalteter Kopie (eine noch offene Kopie kann das Team im Eingabebereich
  ausdrücklich bestätigt trotzdem senden – wie mit gemeinsamen Daten); je Kunde höchstens 30 am Tag. Andere Aufträge werden verworfen, stehen mit Grund beim Vorgang und
  gehen als Sicherheitsereignis ins Protokoll. Abmeldehinweise enthalten nur noch die Kennung des Kunden (Firma und Adresse liest
  der Dienst selbst, nur wenn die Änderung gespeichert ist, höchstens 10 je Kunde und Tag); Benachrichtigungen der Kundenseite nimmt
  der Dienst nur als Sicherheitsereignis an. Bis Trennstufe 2 gilt wie bisher der gespeicherte Originalstand.
- **Grenze, die bleibt:** Eine übernommene Kundenseite kann weiterhin im Namen eines Kunden Bestellwünsche anlegen (Positionen,
  Bemerkung) – die gehen an das Team und als Kopie an die hinterlegte Adresse dieses Kunden, wie bei einem echten Bestellwunsch.
  Firma und Kundennummer stehen weiter außen (Anzeige im Portal). Was die Kundenseite selbst anzeigt, kann sie ohnehin bestimmen.
- **Serverschritt** nach dem Release (Wartungsfenster, Freigabe des Inhabers): `sh deploy/daten-trennen.sh status`, dann
  `trennen` – Sicherung → Stopp → `deploy/daten_trennen.py` (neue interne Dokumente kopieren und vergleichen, dann umschalten, dann
  im gemeinsamen Ordner bereinigen: Originale entfernen, `kunden` und `bestellung` kürzen) → Start. Den Auszug schreibt der
  Postausgang beim ersten Durchgang nach dem Start (bis dahin, wenige Sekunden, gilt kein Sonderposten als ausverkauft).
- **Rückfall:** auf ein Release mit Trennstufe 1 (Stufe 2a) oder älter: vorher `sh deploy/daten-trennen.sh zusammenfuehren` (setzt
  `kunden` und `bestellung` wieder zusammen, entfernt den Auszug), dann das Release, dann – falls es eine Trennung kennt – erneut
  `trennen` mit dessen Stand. Offene Bestellwünsche mit offenem Auftrag (ohne Empfänger) verarbeitet ein älterer Stand nicht; sie
  stehen in den Bestellwünschen und lassen sich nach dem Wiedereinspielen nachsenden.
- **Geprüft:** `tests/deploy/test_daten_trennen.py` (Stufe 0→2 und 1→2 in Dateien und SQLite, Wiederholung nach Abbruch ohne
  Verlust, Zusammenführen mit vollständigem Kundendokument, gleiche Einteilung in PHP und Python je Stufe, Speichern beider Seiten),
  `tests/regeln/test_regeln.py` (`trennstufe`, `felder_kundenseite`), E2E-Gruppe `datentrennung` auf Trennstufe 2 (Kundenseite
  ohne eine einzige Anfrage nach internen Dokumenten; gefälschte Aufträge im gemeinsamen Ordner – fremde Empfänger, fremder Inhalt,
  gefälschter Abmeldehinweis, fremde Benachrichtigung – gehen nicht hinaus; Originalempfänger nach einer Änderung; Auszug ohne
  Mengen), `postausgang`, `order_outbox` und die übrige Suite auf Stufe 0.
- **Offen (eigene Schritte):**
  - Protokoll: erledigt mit Stufe 2d (Trennstufe 4); Anmeldeversuche, Zähler und Live-Verkehr: erledigt mit Stufe 2e (Trennstufe 5).
    Gemeinsam bleiben bewusst die Sperrliste (`sperrliste`: eine von der Kundenseite gesperrte Angreifer-Adresse soll überall gesperrt
    sein), die Länderzählung und die Anmeldeorte der Kunden.
  - Veröffentlichte Einstellungen, die auch die Mitarbeiterseite liest (`sicherheit`, `firewall`, `wartung`, `angebote`, `angebot`,
    `fracht` …), lagen beschreibbar im gemeinsamen Ordner – erledigt mit Stufe 2c (Trennstufe 3, nächster Abschnitt). Zähler und
    Listen, die die Kundenseite selbst schreibt (`sperrliste`, `laendersperre`, `anmeldenamen` …), bleiben gemeinsam.

### Stufe 2c – Trennstufe 3: Veröffentlichtes kann die Kundenseite nicht verändern (umgesetzt, Serverschritt mit Freigabe)

Nach Stufe 2b lagen Dokumente, die die Mitarbeiterseite veröffentlicht und selbst wieder liest, nur im gemeinsamen Ordner:
Angebote und Einzelangebote, Einstellungen der Sicherheit, Firewall, Bedrohungsliste, Notfallmodus, Wartung, Fracht, Bestellfunktion,
der Artikelauszug und das Lebenszeichen des Postausgangs. Eine übernommene Kundenseite hätte sie verändern können – etwa
Sicherheitseinstellungen abschwächen, die Wartung oder den Notfallmodus beenden oder Angebotsnamen ändern, die in Mails stehen.

- **Bereich `veroeffentlicht`** (`regeln/datenverantwortung.toml`, `trennstufe = 3`, erzeugt `DATEN_VEROEFFENTLICHT`): Die
  Mitarbeiterseite und der Postausgang schreiben und lesen diese Dokumente im internen Ordner (maßgeblicher Stand) und legen nach
  jedem Speichern eine Kopie in den gemeinsamen Ordner (`store_kopie`; in einer Transaktion erst nach deren Abschluss, mit dem
  dann aktuellen Stand – eine zurückgesetzte Änderung erreicht die Kopie nie). Die Kundenseite liest nur die Kopie; schreiben,
  sperren oder löschen bricht ab (`StoreKeinZugang`). Gemessen: Keine Kundenaktion schreibt eines dieser Dokumente.
- **Abgleich:** Der Postausgang vergleicht bei jedem Durchgang (alle 5 Sekunden) jede Kopie mit dem internen Stand
  (`store_kopien_abgleichen`). Weicht sie ab, stellt er sie wieder her; ist sie deutlich nach dem internen Stand geschrieben worden
  (also nicht von der Mitarbeiterseite), meldet er das als Sicherheitsereignis („Veröffentlichte Daten im gemeinsamen Ordner
  verändert …“, Benachrichtigung „Sicherheitsereignisse“).
- **Wirkung:** Was die Mitarbeiterseite und der Postausgang lesen, kann die Kundenseite nicht mehr beeinflussen. Was sie Kunden
  anzeigt, kann eine übernommene Kundenseite ohnehin bestimmen – dauerhaft verändert bleibt davon nichts.
- **Serverschritt:** wie bisher `sh deploy/daten-trennen.sh trennen` (kopiert die veröffentlichten Dokumente nach innen; die Kopie
  bleibt). Von Stufe 1 aus geht es in einem Schritt auf Stufe 3. `bestellung` wird dabei innen **und** außen ohne Adressen (mit
  Anzahl) gespeichert. Bis 05.11.2026 kürzte das Werkzeug nur die Kopie außen; der Postausgang stellte sie dann aus dem internen
  Stand wieder her – mit Adressen und ohne Anzahl, die Kundenseite sah 0 Empfänger (Bestellfunktion aus). Behebung auf einem so
  getrennten Server: Bestell-Einstellungen im Eingabebereich einmal speichern oder mit dem korrigierten Stand erneut `trennen`.
- **Rückfall:** `sh deploy/daten-trennen.sh zusammenfuehren` – der interne Stand ersetzt dabei die Kopie im gemeinsamen Ordner.
- **Geprüft:** `tests/deploy/test_daten_trennen.py` (Stufe 2→3 in Dateien und SQLite: Kopie und interner Stand, Transaktion
  zurückgesetzt, Löschen, Kundenseite kann nicht schreiben/sperren/löschen, veränderte und gelöschte Kopie wiederhergestellt und
  erkannt, Zusammenführen mit internem Stand), `tests/regeln/test_regeln.py`, E2E-Gruppe `datentrennung` auf Stufe 3 (veränderte
  Bestell- und Sicherheitseinstellungen im gemeinsamen Ordner: Mitarbeiterseite unbeirrt, Postausgang stellt her und meldet,
  Kundenseite sieht danach die echte Einstellung; Fracht speichern erreicht die Kopie).

### Stufe 2d – Trennstufe 4: Protokoll der Mitarbeiterseite innen (umgesetzt, Serverschritt mit Freigabe)

Das Änderungsprotokoll (`protokoll/<Monat>`) enthielt Einträge beider Seiten – auch Änderungen an Kunden (vorher → nachher, z. B.
E-Mail und Anschrift), Nutzern, Rechten und Personal sowie Namen und Adressen der Mitarbeiter. Die Kundenseite konnte es lesen.

- Ab Trennstufe 4 liegt `protokoll/*` innen (`trennstufe = 4`). Die Kundenseite schreibt ihre eigenen Einträge (Anmeldungen,
  Fehlversuche, Bestellwünsche, Abmeldungen, Passwörter der Kunden) in `kundenprotokoll/<Monat>` im gemeinsamen Ordner und sieht das
  Protokoll der Mitarbeiterseite nicht mehr.
- Die Mitarbeiterseite liest beide zusammen, zeitlich sortiert (`protokoll_monat`, `protokoll_monate`) – Protokollansicht,
  Sicherheitsübersicht und Diagnose zeigen wie bisher alles. Die Aufbewahrung (laufender Monat und sechs davor) gilt für beide.
- Neu: Präfix-Stufen im Regelwerk (`DATEN_AB_STUFE_PRAEFIX`) für Muster wie `protokoll/*`.
- **Serverschritt:** `sh deploy/daten-trennen.sh trennen` (verschiebt `protokoll/*` nach innen). **Rückfall:** `zusammenfuehren`
  vereint beide Protokolle wieder zu `protokoll/*` (zeitlich sortiert; ein wiederholter Lauf fügt nichts doppelt hinzu).
- **Geprüft:** `tests/deploy/test_daten_trennen.py` (Stufe 3→4 in Dateien und SQLite: Umzug, Kundenseite schreibt und sieht nur das
  eigene Protokoll, Mitarbeiterseite liest beide, Aufbewahrung, Zusammenführen), E2E-Gruppe `datentrennung` auf Stufe 4
  (Kundenprotokoll ohne Einträge der Mitarbeiterseite, Protokollansicht zeigt beide).

### Stufe 2e – Trennstufe 5: Anmeldeversuche, Zähler und Live-Verkehr je Seite (umgesetzt, Serverschritt mit Freigabe)

`logins` (Fehlversuche und Sperren je Adresse), `anmeldenamen` (Fehlversuche je Benutzername), `fw_zaehler` (Firewall-Zähler je
Adresse) und `verkehr` (Live-Verkehr: Adresse, aufgerufene Aktion, Benutzername des Mitarbeiters) schrieben beide Seiten in dasselbe
Dokument im gemeinsamen Ordner – die Kundenseite konnte Adressen und Aktionen der Mitarbeiter lesen.

- Ab Trennstufe 5: Bereich `je_seite` – jede Seite schreibt ihr eigenes Dokument gleichen Namens (Kundenseite außen,
  Mitarbeiterseite und Postausgang innen); `store_read`/`store_write`/`with_lock` wählen es selbst, Fachcode unverändert. Die
  Mitarbeiterseite liest das der Kundenseite zusätzlich (`store_aussen_lesen`: Live-Verkehr, Lagebild, Sperren in der Übersicht,
  Diagnose) und ändert es nur beim Aufheben einer Sperre (`store_aussen_aendern`). Jede Seite bremst ihre eigenen Fehlversuche.
- **Serverschritt:** `trennen` verschiebt die bisherigen (gemischten) Dokumente nach innen; die Kundenseite beginnt mit leeren
  Zählern. **Rückfall:** `zusammenfuehren` vereint beide Fassungen (Listen zeitlich, sonst je Schlüssel).
- **Geprüft:** `tests/deploy/test_daten_trennen.py` (Stufe 4→5 in Dateien und SQLite: Umzug, jede Seite liest/schreibt nur ihre
  Fassung, Mitarbeiterseite sieht beide und hebt Sperren der Kundenseite auf, Zusammenführen), E2E-Gruppe `datentrennung` auf Stufe 5
  (Anmeldung der Mitarbeiter nur im internen Live-Verkehr), `schutz`, `anmeldebremse`, `sicherheit_*`. Dazu wie im Betrieb: von
  Stufe 1 in einem Schritt auf Stufe 5 und mit `zusammenfuehren` zurück – alle Dokumente danach wie vorher (Dateien und SQLite).

### Härtung des Kundencontainers (umgesetzt 06.11.2026, wirksam mit dem Release)

Stufe 1 und 2 regeln, **was** die Kundenseite sieht. Die Härtung regelt, was ein Angreifer **tun** könnte, der Code im Prozess
der Kundenseite ausführt: Er soll weder root sein noch Sonderrechte haben, nichts nachladen oder starten und keine
Verbindung nach außen aufbauen können – und so möglichst nichts in der Hand haben, um aus dem Container auszubrechen.

| | vorher | jetzt |
| --- | --- | --- |
| Benutzer | Apache-Hauptprozess root, Arbeitsprozesse `www-data` | alle Prozesse `www-data` (`user: "33:33"`) |
| Linux-Sonderrechte (Capabilities) | Docker-Standard (14, u. a. `CHOWN`, `SETUID`, `NET_RAW`) | keine (`cap_drop: ALL`); Port 80 über die Einstellung des eigenen Netz-Namensraums (`net.ipv4.ip_unprivileged_port_start=0`) |
| Rechteausweitung | `no-new-privileges` | unverändert; dazu Standardprofil seccomp (und AppArmor, wo der Server es hat) |
| Dateisystem | nur lesbar; `/tmp`, `/run` im Speicher | dazu `/tmp` und `/run` mit `noexec,nosuid,nodev` – dort abgelegte Programme lassen sich nicht starten |
| Netz | `default` mit Caddy, Ausgang ins Internet | `kunde` (`internal: true`) nur mit Caddy: kein Ausgang, kein DNS nach außen, Mitarbeiterseite, Keycloak und Postausgang nicht auffindbar |
| Weg nach außen | beliebig | nur das Relais in Caddy (`http://:8081`, nicht veröffentlicht): `GET /range/<5 Hex-Zeichen>` an `api.pwnedpasswords.com` für die Datenleck-Prüfung der Kundenpasswörter (`WA_PWNED_URL`), alles andere 404 |
| PHP (nur Kundenseite, `deploy/anmeldung/kunde-php.ini` über `PHP_INI_SCAN_DIR`) | Image-Standard | keine Programme (`exec`, `system`, `proc_open`, `popen` …), kein `mail()`, `putenv`, `symlink`, `phpinfo`; Dateien nur unter `/var/www/html` und `/tmp` (`open_basedir`); keine Uploads; `expose_php`, `display_errors` aus |
| Apache (nur Kundenseite, `deploy/anmeldung/kunde-apache.conf`) | `ServerTokens OS`, Signatur an | ohne Version und Signatur, kein `TRACE` |

- **Unverändert:** Code und Logik (die Anwendung nutzt keine der gesperrten Funktionen und kein `$_FILES`), der Datenordner
  (PHP schrieb schon bisher als `www-data`), die Mitarbeiterseite und der Postausgang. Die Datenleck-Prüfung läuft weiter –
  fällt das Relais aus, wird sie wie bisher übersprungen und blockiert keine Anmeldung.
- **Bewusst nicht:** `userns-remap` bzw. Docker ohne root – das ist eine Einstellung des ganzen Docker-Dienstes (alle Container,
  Volumes und Rechte im Datenordner) und bringt wenig, solange der Prozess ohnehin nicht root ist. Gegen eine Lücke im Kernel
  selbst schützt nur ein eigener Server für die Kundenseite (offen, Entscheidung des Inhabers).
- **Betrieb:** kein Konsolenschritt. Der Release ändert die Ergänzungsdatei und das Caddyfile, der Release-Modus erstellt alle
  Container neu (dabei entsteht das Netz `kunde`) und prüft die Kundenseite; schlägt das fehl, geht er automatisch zurück. Nach
  einem Rückfall auf einen Stand davor bleibt das Netz `kunde` ungenutzt stehen (ohne Wirkung, entfernen mit
  `docker network prune`). `deploy/datenbank-umschalten.sh` und die Notfallwerkzeuge (`-u www-data`) arbeiten unverändert.
- **Geprüft:** `tests/deploy/test_kundencontainer.sh` (CI, Auftrag „Anwendungs-Image prüfen“: Compose-Einstellungen, Prozesse,
  Sonderrechte, nur lesbar, `noexec`, kein Ausgang, Relais nur für `/range/`, PHP- und Apache-Einstellungen, Kundenseite arbeitet:
  Startseite, Status, Angebot, Kundenanmeldung mit Sitzung und Schreiben im Datenordner, keine Fehler im Protokoll),
  `deploy/anmeldung/pruefen.sh` (Start wie im Betrieb), `tests/deploy/test_cdn.py` (Relais im Caddyfile, Port nicht veröffentlicht).

## Wirkung

| Wenn die Kundenseite geknackt würde | vorher | nach Stufe 1 | nach Stufe 2 |
| --- | --- | --- | --- |
| Personaldaten, Mitarbeiterkonten, CRM, Controlling, QS-Dokumente lesen | ja | ja (gemeinsamer Datenordner) | nein (2a) |
| Kunden-Warenwirtschaftszahlen, Anschriften, Bestand, Einkaufspreise lesen | ja | ja | ja nach 2a, nein nach 2b |
| Sicherheits-, Firewall-, Wartungs- und Notfalleinstellungen oder Angebote dauerhaft verändern | ja | ja | nein nach 2c (Kopie wird wiederhergestellt und gemeldet) |
| Protokoll der Mitarbeiterseite lesen (Änderungen an Kunden, Nutzern, Personal) | ja | ja | nein nach 2d |
| Anmeldeversuche, Zähler und Live-Verkehr der Mitarbeiterseite lesen | ja | ja | nein nach 2e |
| Mitarbeiterkonten in Keycloak übernehmen | ja | nein (kein Geheimnis, kein Netzweg) | nein |
| Anmelde-Geheimnisse der Mitarbeiter-Hosts | ja | nein | nein |
| Postfach-Passwort | ja | ja – nein seit dem Postausgang von innen (nach `postfach-schluessel.sh umziehen`) | nein |
| E-Mails über das Firmenpostfach an beliebige Empfänger, mit beliebigem Inhalt | ja | ja – auch mit Postausgang, über gefälschte Aufträge im gemeinsamen Datenordner | nein (2b): nur Bestellwünsche im Namen eines Kunden an Team und dessen hinterlegte Adresse, höchstens 30 am Tag |
| Dateien der Anwendung verändern | nein (nur lesend) | nein | nein |
| Mitarbeiter-Hosts durch Überlast ausbremsen | ja | nein (Grenzen) | nein |
| Als root arbeiten oder Linux-Sonderrechte nutzen (Grundlage vieler Ausbrüche aus dem Container) | ja | ja | nein seit der Härtung |
| Programme starten, Werkzeuge nachladen und ausführen | ja | ja | nein seit der Härtung (PHP ohne `exec` & Co., `/tmp` ohne Ausführung) |
| Daten direkt an fremde Server schicken oder von dort holen | ja | ja | nein seit der Härtung (Netz ohne Ausgang, nur das Relais der Datenleck-Prüfung) |

Unabhängig von der Kundenseite – mit erbeutetem Geheimnis des Dienstkontos `konten`: vor Stufe 1b jedes Konto des Realms
`mitarbeiter` übernehmbar, danach nur noch Konten ohne Administratorrolle; als Administrator anmelden kann sich damit
niemand (Stufe 1b).

## Alternativen

| Alternative | Bewertung |
| --- | --- |
| Nur das Dienstkonto beschneiden | sinnvoll und als Stufe 1b umgesetzt, ersetzt aber die Trennung nicht |
| Eigene Kunden-Anwendung mit eigenem Code | verworfen: Angebots- und Preislogik (`offer_resolve`) gäbe es doppelt und liefe auseinander |
| Container je Modul | verworfen (Zielarchitektur §1): vervielfacht Betrieb ohne Gewinn – die Grenze, die zählt, ist öffentlich ↔ intern |

## Betrieb

- **Einführung:** Mit dem Release ändert sich die Ergänzungsdatei – der Release-Modus erstellt dann wie bei jeder solchen
  Änderung alle Container neu (`docker compose up -d --force-recreate`); kein eigener Konsolenschritt. Keycloak startet dabei
  wegen des neuen Netzes neu (rund eine Minute keine neue Mitarbeiteranmeldung; laufende Sitzungen bleiben). Die Prüfung nach
  dem Einspielen fragt beim ersten Mal nur die Kundenseite ab (es läuft noch das Release-Skript des alten Stands); danach
  einmal `dashboard-stafl.de` aufrufen und anmelden.
- **Ab dem folgenden Release** prüft der Release-Modus nach dem Einspielen auch die Mitarbeiter-Hosts und kehrt zurück, wenn
  ihr Container nicht antwortet. Neues Image: beide Anwendungs-Container neu; nur `apache-oidc.conf`: nur `app-mitarbeiter`.
- **Rückfall:** Ein automatischer oder manueller Rückfall auf einen Stand vor ADR-007 lässt den Container `app-mitarbeiter`
  als verwaisten Container stehen (keine Wirkung, Caddy erreicht ihn dann nicht mehr). Aufräumen:
  `docker compose up -d --remove-orphans`.
- **Geänderte Anmelde-Werte in `.env`** liest die Anwendung nach `docker compose up -d app-mitarbeiter` (bisher `app`).
- **Speicher umschalten** (`deploy/datenbank-umschalten.sh`) stoppt beide Anwendungs-Container und den Postausgang; mit
  getrennten Daten erst `daten-trennen.sh zusammenfuehren` (Stufe 2a).
- **Daten trennen:** `sh deploy/daten-trennen.sh status` (Stufe und Plan, ändert nichts), `trennen` (auf die höchste Stufe des
  eingespielten Stands), `zusammenfuehren` – Abschnitte Stufe 2a und 2b.
- **Ein Vorgang über beide Datenbanken** (z. B. Veröffentlichen bis Trennstufe 2: Entwurf innen, Angebot und Protokoll außen; ab
  Stufe 2: Kunden außen, Stammdaten innen): Die äußerste Sperre schließt beide Datenbanken gemeinsam ab bzw. setzt beide zurück
  (`with_lock_in`, `store_beitreten`). Vorher blieb bei einem Fehler mitten im Vorgang der schon geschriebene Teil der anderen
  Datenbank gespeichert (seit Stufe 2a, z. B. ein veröffentlichtes Angebot ohne gesicherte Vorversion). Zwei SQLite-Dateien lassen
  sich nicht in einem einzigen Schritt abschließen – offen bleibt nur ein Fehler genau zwischen den beiden Abschlüssen.
- **Prüfung in der CI:** Die volle E2E-Suite läuft zusätzlich mit getrennten Daten (SQLite wie auf dem Server, höchste
  Trennstufe des Stands, `WA_TEST_TRENNUNG=1`, Aufträge „Ende-zu-Ende-Tests (sqlite, getrennt, Teil k/3)“). So fällt vor dem
  Merge auf, wenn neuer Code Daten am falschen Ort erwartet oder die Kundenseite interne Dokumente braucht.
- **Postausgang:** `docker compose ps postausgang` (Zustand „healthy“ = Lebenszeichen frisch), `docker compose logs postausgang`
  (je Durchgang mit Versand eine Zeile). Steht der Dienst länger als 15 Minuten, nimmt das Portal keine Bestellwünsche an.
  Einführung: Release einspielen (erstellt den Dienst), danach einmal `sh deploy/postfach-schluessel.sh umziehen`.
- **Ressourcen:** Server Hostinger KVM 8 (8 vCPU, 32 GB). Grenzen der Kundenseite: 3 CPU, 4 GB, 1024 Prozesse
  (`KUNDEN_CPUS`, `KUNDEN_SPEICHER` in `.env`). Der zweite Container braucht im Leerlauf rund 100–200 MB.
