# Funktionen: Plattformkern (`plattform`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

103 Dateien, 961 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `.github/scripts/apt_vorrat.py`

_Paketvorrat für die CI: heruntergeladene Debian-Pakete (.deb) zwischen Läufen aufbewahren._

- `dateiname_lesen(name)` – „paket_version_arch.deb“ (Version mit %3a statt „:“) → (paket, version, arch) oder None.
- `eintraege(text)` – Ausgabe von `apt-cache show` → {(paket, version, arch): {sha256, …}}.
- `sha256(pfad)`
- `einsetzen(ordner)`
- `sammeln(ordner)`
- `main(argv)`

## `.github/scripts/ci_nachweis.py`

_Nachweis „schon im Pull Request vollständig geprüft“ für einen Commit auf main (ci.yml, Auftrag „nachweis“)._

- `nachweis_name(tree)`
- `gh_api(pfad)`
- `auftraege_pruefen(jobs, tree)` – None, wenn die Aufträge eines Laufs eine vollständige Prüfung von `tree` belegen; sonst der Grund.
- `lauf_pruefen(lauf, repo, kopf)` – None, wenn der Lauf grundsätzlich als Nachweis in Frage kommt; sonst der Grund.
- `suchen(api, repo, sha, tree, log)` – → (Lauf oder None, Grund).
- `main(argv, api)`

## `app/api/aktionen/anmeldekonten.php`

_Aktionen: Konten der zentralen Anmeldung (Keycloak) aus Verwaltung → Mitarbeiter (nur Administratoren). anmeldekonto (lesen)_

- `anmeldekonto_nutzer(id)` – Mitarbeiterkonto zur Kennung oder 404
- `anmeldekonto_nur_temporaer(u)` – Administratoren und Konten mit Pflicht zum zweiten Faktor: Passwort nur vorübergehend setzen (muss bei der nächsten Anmeldung geändert werden) – sonst kennte …

## `app/api/geo.php`

_Länderzuordnung von IP-Adressen (für Ländersperren) Datenquelle: ip-location-db „geo-whois-asn-country“ (CC0 / Public Domain) Binärformat laender.dat.php (beginnt mit einer PHP-Sperre, damit die Datei im Browser …_

- `geo_file()` – aktuelle Datenbank: heruntergeladenes Update (Datenordner) vor mitgelieferter Fassung
- `geo_info()`
- `geo_country(ip)` – ISO-Ländercode einer IP-Adresse oder null (privat/unbekannt)
- `geo_inc8(b)` – 8-Byte-Wert + 1 (für zusammenhängende Bereiche)
- `geo_build(in4, in6, out, date)` – CSV (start,ende,Land) → Binärdatei; benachbarte Bereiche desselben Landes werden zusammengefasst
- `geo_download(out)` – neueste Länderdaten herunterladen und in den Datenordner schreiben

## `app/api/lib/adressen.php`

_Adressen → Koordinaten auf dem eigenen Server (Plattformkern, genutzt von der CRM-Karte) Schlägt Straße + Hausnummer + PLZ/Ort in einem Adressverzeichnis aus OpenStreetMap nach (ODbL; erzeugt von …_

**Schreibweisen (wie deploy/karte/adressen.py)**

- `adressen_klein(s)`
- `adressen_norm_text(s)`
- `adressen_norm_strasse(s)`
- `adressen_norm_nr(s)`
- `adressen_norm_plz(s)`
- `adressen_teilen(feld)` – Straßenfeld der Stammdaten („Hauptstr. 12 a“, „Am Markt 3-5“) → [Straße, Hausnummer]; ohne Nummer: [Straße, '']

**Verzeichnis**

- `adressen_pfad()`
- `adressen_db()` – Verbindung (nur lesend) oder null, wenn die Datei fehlt oder ein unbekanntes Format hat
- `adressen_stand()` – Stand des Verzeichnisses für die Oberfläche: ['adressen' => n, 'erzeugt' => 'JJJJ-MM-TT'] oder null
- `adressen_punkt(strasseFeld, plz, ort)` – Koordinate einer Anschrift: ['lat' => …, 'lon' => …, 'genau' => 'haus'\|'strasse'] oder null (unbekannt/keine Datei)

## `app/api/lib/anmeldekonten.php`

_Konten der zentralen Anmeldung (Keycloak, Realm „mitarbeiter“) aus der Verwaltung steuern – EIN Passwort für alles._

- `__construct(meldung, status)`
- `konten_einstellung()` – Einstellungen: Adresse von Keycloak im internen Netz (Betrieb http://keycloak:8080) und Geheimnis des Clients
- `konten_eingerichtet()`
- `konten_http(methode, url, inhalt, kopf)` – Eine Anfrage an Keycloak: [Status, JSON\|null, Kopfzeilen].
- `konten_token()` – Zugangstoken des Clients „konten“ (client_credentials), nur im Speicher dieser Anfrage
- `konten_api(methode, pfad, daten)` – Aufruf der Verwaltungsschnittstelle des Realms: $pfad relativ zu /admin/realms/<realm>/
- `konten_finden(u)` – Keycloak-Konto zum Mitarbeiterkonto: [Konto\|null, Hinweis, Altkonto\|null].
- `konten_status(u)` – Zustand für die Verwaltung (nur lesen)
- `konten_pflicht(u)` – Vorhandenes Konto oder Fehler (für schreibende Funktionen)
- `konten_min_laenge()` – Mindestlänge für Passwörter der zentralen Anmeldung: Einstellung „Passwörter mindestens … Zeichen“, nie unter 12 (Grundwert des Realms).
- `konten_passwort_meldung(j)` – Richtlinienfehler von Keycloak (Passwort) auf Deutsch
- `konten_startpasswort()` – Gut vorlesbares Startpasswort wie konten.sh (mindestens 16 Zeichen in Vierergruppen, ohne 0/O/1/l/I), immer mit Groß- und Kleinbuchstaben und Ziffer – …
- `konten_passwort(u, passwort, temporaer)` – Passwort setzen; $temporaer = bei der nächsten Anmeldung ändern.
- `konten_entsperren(u)` – Sperre nach Fehlversuchen aufheben (und ein in Keycloak gesperrtes Konto wieder aktivieren, wie konten.sh entsperren)
- `konten_link(u)` – Mail mit Link zum Passwort-Festlegen (72 Stunden, nur „Passwort aktualisieren“)
- `konten_anlegen(u)` – Fehlendes Konto anlegen (Benutzername, Name, E-Mail aus dem Mitarbeiterkonto) und verknüpfen.
- `konten_entfernen(u)` – Mitarbeiter gelöscht (Aktion user_delete, nach dem Löschen aufgerufen): Konto in der zentralen Anmeldung mitlöschen – sonst bliebe es bestehen und ein später …

## `app/api/lib/benachrichtigung.php`

_Benachrichtigungen an Mitarbeiter (E-Mail): welche Ereignisse an wen gehen, legt der Administrator fest._

- `notify_settings()` – Gespeicherte Einstellungen: ['events' => [ereignis => ['on' => bool, 'to' => [...]]], 'updatedAt', 'updatedBy'].
- `notify_view()`
- `notify_targets(ev, evenIfOff)` – Empfänger eines Ereignisses (leer = keine E-Mail); berücksichtigt den Ersatz (Antwortadresse)
- `notify_parse_to(raw, what)` – Empfängerliste aus Text oder Liste prüfen (Komma, Semikolon, Leerzeichen); doppelte entfernt
- `notify(ev, title, facts)` – Ereignis vormerken; versendet wird nach der Antwort (notify_flush)
- `notify_from_audit(a, s, d, who)` – Aus dem Protokoll: passende Vorgänge als Ereignis melden (Wer, IP, Änderungen)
- `notify_mail(ev, items, skipped, test)` – Inhalt einer Benachrichtigung: [Betreff, Text, HTML]
- `notify_send(ev, to, items, skipped, test, by, inhalt)` – An die Empfänger eines Ereignisses senden und im Versandprotokoll vermerken; Ergebnis je Empfänger.
- `notify_flush()` – Nach der Antwort: vorgemerkte Ereignisse je Art bündeln, Pause beachten, versenden.

## `app/api/lib/bereitschaft.php`

_Bereitschaft für den Ernstfall (Oberfläche_

- `bereit_dok()`
- `bereit_aendern(fn)` – Ändern unter Sperre: $fn(array &$d) – Rückgabe von $fn wird weitergereicht

**Leitfaden**

- `leitfaden()`
- `leitfaden_speichern(me, b)` – Speichern (Administrator).
- `leitfaden_haken_fuer(seit)` – Abgehakte Schritte eines Notfalls (Schlüssel: Beginn des Notfalls)
- `leitfaden_haken(me, b)` – Schritt im laufenden Notfall abhaken bzw. zurücknehmen ($b: schritt, erledigt)

**Probealarm**

- `bereit_proben()`
- `probe_pruefung()` – Bereitschaftsprüfung: [{k, stufe ok\|warn\|bad\|info, titel, text, hinweis}]
- `probe_ausloesen(me)` – Probealarm auslösen ($me: sicherheit.notfall oder Administrator).
- `probe_offen(me)` – Offener Probealarm für $me (jünger als 24 Stunden, nicht selbst ausgelöst, noch nicht bestätigt)
- `probe_quittieren(me, id)` – „Probealarm gesehen“: Reaktionszeit vermerken
- `bereit_dauer(s)`

**Wochenbericht**

- `bericht_einstellungen()`
- `bericht_anzeige()` – Anzeige für das Modul: Einstellungen, Empfänger, nächster automatischer Versand
- `bericht_naechster(e)` – Nächster automatischer Versand (Ortszeit, ISO 8601): in dieser Woche schon vermerkt → eine Woche später, sonst der Berichtstag dieser Woche bzw. – wenn der …
- `bericht_speichern(me, b)`
- `bericht_daten()` – Inhalt des Berichts (letzte 7 Tage) – Abschnitte mit Zeilen [Bezeichnung, Wert, Stufe] und Listen; eine Quelle für E-Mail und Modul
- `bereit_link(reiter)` – Adresse der Sicherheitszentrale für Links in E-Mails (Modulregister; nie aus der Anfrage)
- `bereit_mail(titel, einleitung, abschnitte, reiter)` – E-Mail im Stil der Benachrichtigungen: [Betreff, Text, HTML].
- `bericht_senden(me, auto)` – Bericht senden ($me = null: automatischer Versand).
- `bericht_vermerken(e)`
- `bericht_anstossen()` – Automatischer Versand: von der Statusabfrage angemeldeter Mitarbeiter aufgerufen (api status).

## `app/api/lib/bestand-mhd.php`

_Modul Bestand · MHD-Liste an den Verkauf: dieselbe Liste wie die Suche „MHD“ im Bestand (kürzestes MHD bis heute + 14 Tage, früheste zuerst), als Excel-Datei (ohne PHP-Erweiterung „zip“, unkomprimiertes ZIP) und …_

- `mhd_stufe(mhd, heute)` – MHD-Stufe wie in der Oberfläche (mhdClass in admin.js)
- `mhd_preise(woche)` – Wochenpreis je Artikelnummer wie S.weekPriceMap: bei widersprüchlichen Angaben „mehrere Preisangaben“
- `mhd_preis_text(p)`
- `mhd_liste(st, mitPreisen, jetzt)` – Die MHD-Liste: [heute, bis, zeilen[{code, name, kg, mhd, mhdKg, stufe, erfasst, gesamt, eta, preis, vorwoche}], preise(bool), wochen] „name“ ist die …
- `mhd_liste_ohne_preise(jetzt)` – Schnittstelle für andere Module (GR-101; Leser „crm“ in regeln/datenverantwortung.toml, CRM-Reiter „MHD-Ware“): die heutige MHD-Liste ohne Preise und …

**Excel (Office Open XML, ein Blatt)**

- `mhd_zip(dateien)`
- `mhd_xml(t)`
- `mhd_spalte(n)`
- `mhd_xlsx(l, titel)`
- `mhd_bild_pruefen(b64)` – Bild der Liste aus dem Browser prüfen (nur PNG, Größe begrenzt; der Browser zeichnet in drei- oder zweifacher Auflösung).
- `mhd_mail(l, png, notiz, me, st, breite)` – E-Mail an den Verkauf: Text, HTML mit eingebettetem Bild (cid), Excel im Anhang.

## `app/api/lib/dateiablage.php`

_Dateiablage der Plattform (neben der Speicherschicht): hochgeladene Dateien eines Moduls (z._

**Pfade und Namen**

- `ablage_wurzel()`
- `ablage_bereich(bereich)`
- `ablage_pfad(bereich, id)`
- `ablage_neue_id()`
- `ablage_dateiname(v)` – Dateiname für Anzeige und Download: ohne Pfad, Steuer- und unter Windows verbotene Zeichen, höchstens 150 Zeichen, Endung bleibt erhalten.
- `ablage_art(name)` – Endung → Art (Schlüssel in ABLAGE_ARTEN) oder Ausnahme
- `ablage_inhalt_passt(pfad, art)` – Passt der Dateikopf zur Endung?

**Hochladen in Teilen**

- `ablage_teile_ordner()`
- `ablage_aufraeumen()` – Unvollständige Uploads nach ABLAGE_UPLOAD_STUNDEN entfernen
- `ablage_teil(bereich, nutzerId, ziel, b)` – Einen Teil annehmen.
- `ablage_upload_verwerfen(upload)`

**Lesen, Ablegen, Kopieren, Entfernen, Ausliefern**

- `ablage_vorhanden(bereich, id)`
- `ablage_lesen(bereich, id)` – Inhalt lesen (z. B. eine Vorlage zum Ausfüllen) oder null, wenn die Datei fehlt
- `ablage_ablegen(bereich, inhalt)` – Vom Server erzeugten Inhalt (z. B. eine ausgefüllte Vorlage) als neue Datei ablegen: ['id', 'groesse', 'sha256']
- `ablage_kopieren(bereich, id)` – Datei unter neuer Kennung kopieren (z. B. in eine neue Version): ['id', 'groesse', 'sha256'] oder null, wenn sie fehlt
- `ablage_entfernen(bereich, id)`
- `ablage_disposition(name)` – Content-Disposition mit ASCII-Ersatz und UTF-8-Namen (RFC 6266/5987)
- `ablage_senden(bereich, id, name, mime)` – Datei als Download senden und beenden; fehlt sie, 404 (JSON)

**ZIP-Export (Methode „stored“, ohne Zip64)**

- `ablage_zip_pfad(teil)`
- `ablage_zip_senden(dateiname, eintraege)`

## `app/api/lib/diagnose.php`

_Sicherheit für IT-Administratoren_

- `sec_log_entries(days)` – Protokolleinträge der letzten $days Tage (Monatsdateien)
- `sec_timeline(entries)` – Verlauf der letzten 14 Tage je Tag: fehlgeschlagene Anmeldungen (Mitarbeiter/Kunden), Passwortbestätigung, Ländersperre
- `sec_top_ips(entries)` – Auffällige Adressen (7 Tage): fehlgeschlagene Anmeldungen je IP mit Land und versuchten Benutzernamen
- `betrieb_daten(me)` – Betriebszustand (Modul Sicherheit: Reiter System und Lagebild): Wartung, Sicherung, Bereitstellung, Datenablage, Speicher, E-Mail-Versand, Bestellwünsche, …
- `sec_config_checks(users)` – Konfigurationsprüfung (serverseitig sichtbar): [bereich, stufe ok\|warn\|bad\|info, titel, befund, empfehlung]
- `sec_diag(check)` – Nur lesende Diagnosen; Ergebnis: ['ok' => bool, 'items' => [[label, wert, stufe]], 'ms' => int]
- `sec_export_csv(days)` – Sicherheitsprotokoll als CSV (Semikolon, UTF-8 mit BOM)

**Modul Sicherheit: Lagebild, Ereignisse, privilegierte Konten (nur lesend; Aufrufer prüfen die Rechte)**

- `sec_ereignis_art(a)`
- `sec_ereignisse(tage, art, q, max)` – Sicherheitsereignisse der letzten $tage Tage, neueste zuerst; Filter Art und Suchtext (Beschreibung, Benutzer, Name, IP)
- `sec_lagebild(me)` – Lagebild: Kennzahlen, Verlauf, auffällige Adressen, Konfigurationsprüfung, Dateiprüfung, letzte Ereignisse
- `sec_ungenutzt(tage, users)`
- `sec_konten()`

## `app/api/lib/firewall.php`

_Schutzzentrale: Firewall (Angriffsmuster), Sperrliste (von Hand, automatisch, Bedrohungsliste), Fallen für Angriffswerkzeuge, Fehlerbremse und Live-Verkehr._

- `fw()`
- `fw_erlaubt(ip)` – Nie sperren: interne Adressen, freigegebene Adressen des Eingabebereichs und die Liste „nie sperren“
- `fw_mitarbeiter()` – Angemeldeter Mitarbeiter?
- `fw_fremd()` – Von einer fremden Seite ausgelöst (z. B. <img src="…/wp-login.php"> oder ein Link)?
- `fw_key(ip)` – Schlüssel einer Adresse: IPv4 einzeln, IPv6 je /64 (wie bei den Anmeldeversuchen)
- `fw_sperrliste()`
- `fw_gesperrt(ip)` – Gesperrt? Liefert den Grund oder null
- `fw_werte(v, out, tiefe)`
- `fw_pruefen(text)`
- `fw_angriff()`
- `fw_zaehlen(ip, art, fenster)` – Zähler (Treffer / Fehler) je Adresse – liefert die Anzahl im Zeitfenster
- `fw_auto_sperren(ip, grund)` – Automatisch sperren (Protokoll → Benachrichtigung „Sicherheitsereignisse“)
- `fw_treffer(ip, grund)`
- `fw_verkehr(e)` – Live-Verkehr: Ringpuffer der letzten Anfragen.
- `fw_guard(action)` – Vor jeder Aktion
- `fw_nachher(action)`
- `fw_falle()` – Falle: typische Pfade von Angriffswerkzeugen (wp-login.php, .env, phpMyAdmin …) leitet Caddy hierher
- `fw_feed_laden()` – Bedrohungsliste herunterladen und prüfen (nur öffentliche Netze, keine eigenen/freigegebenen Adressen)
- `fw_feed_speichern(netze, quelle)`
- `fw_feed_index(netze)` – Schneller Index der Bedrohungsliste für die Prüfung vor jeder Anfrage: IPv4 als sortierte, zusammengefasste Bereiche (gepackt: Anfang/Ende je 4 Byte, base64) …
- `fw_feed_trifft(ip)` – Steht die Adresse auf der Bedrohungsliste?
- `fw_feed_info()`
- `fw_feed_veraltet()` – Bedrohungsliste eingeschaltet, aber noch nie oder vor über einem Tag geladen (Auffrischen: fw_feed_auffrischen)
- `fw_clean(b, old)` – Einstellungen prüfen (Firewall)
- `fw_vorlage_anwenden(k, me, notfall)` – Vorlage anwenden (Aktion fw_vorlage, Notfallmodus lib/notfall.php): Sicherheits- und Firewall-Einstellungen speichern.
- `fw_status(filter)` – Übersicht für die Ansicht „Schutz“
- `fw_zahlen(sekunden)` – Zahlen aus dem Verkehrsprotokoll für einen Zeitraum (Sekunden; Lagebild 24 h, Wochenbericht 7 Tage): Angriffsmuster, abgewiesene Anfragen gesperrter …
- `fw_stunden()` – Verlauf der letzten 24 Stunden je Stunde (älteste zuerst, letzte = laufende Stunde): Angriffsmuster und abgewiesene Anfragen gesperrter Adressen – für das …
- `fw_verkehr_liste(filter, seit)`

## `app/api/lib/geraete.php`

_Vertraute Geräte: Nach einer erfolgreichen Anmeldung merkt sich der Browser eine zufällige Kennung (Cookie, nur für den Server lesbar); gespeichert wird beim Zugang nur deren Prüfsumme._

- `geraet_cookie_name()` – Name des Cookies: über HTTPS „__Host-WA_GERAET“ – eine Subdomain oder ein Angreifer im Netz kann es so nicht setzen
- `geraet_token()` – Kennung aus dem Cookie (nur das Format wird geprüft)
- `geraet_hash(t)`
- `geraete_gueltig(acc)` – Gültige (nicht verfallene) Geräte eines Zugangs
- `geraet_vertraut(acc)` – Ist dieser Browser für den Zugang vertraut (und hat noch Versuche)?
- `geraet_fehlversuch(acc, i)` – Fehlversuch auf einem vertrauten Gerät während einer Sperre zählen
- `geraet_name(ua)` – Kurzer Gerätename für die Anzeige („Chrome · Windows“)
- `geraet_merken(acc, neu)` – Nach einer erfolgreichen Anmeldung: Gerät merken bzw. auffrischen und das Cookie (neu) setzen.
- `geraete_zuruecksetzen(acc, alle)` – Nur das aktuelle Gerät behalten (eigener Passwortwechsel) bzw. alle entfernen ($alle)
- `geraete_public(acc)` – Anzeige in der Verwaltung (ohne Prüfsummen)
- `geraet_neu_melden(u, neu)` – Sicherheitsereignis, wenn sich ein Administrator von einem Gerät anmeldet, das für seinen Zugang noch nicht bekannt war (nicht beim allerersten gemerkten …

## `app/api/lib/herkunft.php`

_Herkunftsprüfung im API-Einstieg (GR-109, ADR-003 §1)_

- `herkunft_eigene()`
- `herkunft_fremd(aktion, method)` – Grund der Abweisung oder null, wenn die Anfrage von der eigenen Seite stammt
- `herkunft_pruefen(aktion, method)` – Abweisen, ohne die Firewall zu belasten: eine fremde Seite darf ihre Besucher nicht sperren lassen (vgl. fw_fremd)
- `host_eigene_seite(oberflaeche)` – Aktion ↔ Host (GR-109, ADR-003 §3): Auf einem Keycloak-Host meldet der Webserver seine Oberfläche (SetEnv WA_OBERFLAECHE, nie aus Kopfzeilen).
- `host_nur_grundaktionen(host)` – Hosts ohne Fachaktionen: das Dashboard (dashboard-stafl.de) braucht nur Status, Modulübersicht, Darstellung und Abmelden.
- `host_fremd(aktion)` – true, wenn die Aktion auf diesem Host nicht angeboten wird
- `host_pruefen(aktion)`

## `app/api/lib/integritaet.php`

_Dateiprüfung (wie ein Datei-Scanner gegen Schadcode): vergleicht die Programmdateien mit der Prüfliste der freigegebenen Fassung (integritaet-liste.php, beim Einspielen aus dem freigegebenen Commit erzeugt von …_

- `integritaet_nur_sperre(t)` – Nur sperrende Zugriffsregeln (.htaccess im Datenordner und im Datenbankordner): jede Zeile ist leer, Kommentar, „Require all denied“, „Deny from all“, „Order …
- `integritaet_proxy_ok(t)`
- `integritaet_art(pfad)` – Dateiart für die Musterprüfung (null = nicht durchsuchen, z. B. Bilder)
- `integritaet_muster(text, art)` – Muster in einem Text: [Bezeichnungen, höchste Stufe]
- `integritaet_liste()`
- `integritaet_pruefen()` – Eine vollständige Prüfung; Ergebnis ohne Dateiinhalte
- `integritaet_komponenten(root)` – Komponenten mit Version und Stand der Sicherheitsupdates (ohne Abfrage im Internet)
- `integritaet_neu(prev, r)` – Neue Befunde (kritisch/Warnung) gegenüber dem vorigen Lauf
- `integritaet_lauf(auto, me)` – Prüfung ausführen, speichern (letzter Lauf + kurzer Verlauf) und bei neuen Befunden benachrichtigen
- `integritaet_stand(autoErlaubt)` – Gespeicherter Stand; ist der letzte Lauf älter als 24 Stunden, wird höchstens einmal am Tag automatisch geprüft

## `app/api/lib/kern.php`

_Antworten, Eingaben, Datenprüfung_

**Hilfsfunktionen**

- `testumgebung()` – Testumgebung (test.<Domain>): nur Testdaten; E-Mails gehen in das Testpostfach statt an echte Empfänger
- `respond(data, status)`
- `fail(msg, status)`
- `body()`
- `now()`
- `utc_monat(versatz, t)` – Monat (UTC, „JJJJ-MM“) relativ zum aktuellen bzw. zu $t – unabhängig von der eingestellten Zeitzone (Monatsdateien des Protokolls sind nach UTC benannt; …

**Datenprüfung**

- `s(v, max, allowEmpty)`
- `clean_price(p, where)`

## `app/api/lib/module.php`

_Modulzustand zur Laufzeit: wer darf welche Oberfläche nutzen (GR-102)? Grundlage ist ausschließlich die erzeugte Liste lib/module-liste.php (Modulregister regeln/module.toml und Entscheidungstabelle regeln/wartung.toml)._

- `modul_freigabe_zulaessig(entwicklung, freigabe)`
- `modul_entscheiden(lage)` – Erste passende Zeile der Entscheidungstabelle.
- `modul_person(u, ziel, freigabe)` – Rolle für die Tabelle (Hinweis zu Regel 4/7 in regeln/wartung.toml): - Testfreigabe: nur eingetragene Tester haben Zugang; Administratoren nur, wenn sie sich …

**Freigabe und Tester zur Laufzeit (Modulverwaltung, Roadmap 5)**

- `modul_dok(neu)` – Dokument „module“ einmal je Anfrage lesen (die Übersicht fragt jede Oberfläche ab); nach eigenem Schreiben neu laden
- `modul_freigabe_aenderbar(o)`
- `modul_freigabe(modul, oberflaeche)`
- `modul_tester(ziel)`
- `modul_freigabe_setzen(ziel, b, me)` – Freigabe setzen ($me: bestätigter Administrator).
- `modul_tester_setzen(ziel, b, me)` – Tester einer Oberfläche festlegen: nur aktive Mitarbeiterkonten; wirkt nur bei Freigabe „test“.

**Wartung je Oberfläche (GR-107)**

- `modul_laufzeit()`
- `modul_wartung_eintrag(modul, oberflaeche)` – Gespeicherte Wartung einer Oberfläche (auch geplante), sonst null
- `modul_wartung(modul, oberflaeche)` – Wirksame Wartung (aktiv und Beginn erreicht)
- `modul_betrieb(modul, oberflaeche)`
- `modul_verlauf_eintragen(eintrag)` – Eintrag in den Verlauf (Dokument „module“) – für alle Oberflächen einschließlich angebot.kunden
- `modul_text(s, max)`
- `modul_zeit(s, feld)`
- `modul_wartung_setzen(ziel, b, me)` – Wartung einer Oberfläche setzen oder beenden ($me: bestätigter Administrator).
- `modul_durchsetzen(aktion)` – Durchsetzung im API-Einstieg (index.php): Aktionen einer Oberfläche, die für den Nutzer gerade nicht zugänglich ist, laufen nicht.
- `modul_wartung_weitere(aktion)` – Weitere Oberflächen, deren Wartung für diese Aktion gilt (siehe modul_durchsetzen)
- `modul_wartung_antwort(modul, oberflaeche)`
- `modul_zustand(modul, oberflaeche, u)`
- `modul_wartung_anzeige(modul, oberflaeche, u)` – Angaben zu einer (auch geplanten) Wartung für die Anzeige; Grund und Urheber nur für Administratoren
- `modul_uebersicht(u)` – Übersicht für das Dashboard und die Modulverwaltung (Aktion module_status, nur angemeldete Mitarbeiter).
- `modul_verwaltung_angaben(modul, oberflaeche, o)` – Angaben für die Modulverwaltung (nur Administratoren): Herkunft der Freigabe, mögliche Werte, Tester mit Namen

## `app/api/lib/notfall.php`

_Notfallmodus (Oberfläche_

- `notfall_dok(neu)` – Gespeicherter Zustand (je Anfrage einmal gelesen; nach Änderungen mit $neu = true)
- `notfall()`
- `notfall_aktiv()`
- `notfall_kundentext(n)`
- `notfall_wartung(modul, oberflaeche)` – Wartungseintrag einer Oberfläche im Notfall (für modul_wartung_eintrag): jede sperrbare interne Oberfläche
- `kunden_wartung_ausnahme(u)` – Wer trotz Wartung der Angebotsseite die Kundenfunktionen nutzt: angemeldete Mitarbeiter (GR-009) – im Notfall nur Administratoren
- `notfall_mail_gesperrt()` – E-Mail-Versand gesperrt?
- `notfall_anzeige(u)` – Anzeige für Status, Dashboard und Modul: alle sehen „aktiv seit“; Grund, Urheber und Wirkung nur Administratoren und Inhaber von …
- `notfall_verlauf()` – Verlauf der letzten Notfälle (ohne Schnappschüsse)
- `notfall_wirkungen()` – Wirkungen als Text (eine Quelle für Oberfläche und Benachrichtigung) und aktuelle Zahlen zur Vorschau
- `notfall_rollen()`
- `notfall_ausloesen(me, b)` – Auslösen. $b: grund (Pflicht), wort (= NOTFALL), kundentext, firewall (Standard an), admins (nur Administratoren: auch andere Administratorsitzungen …
- `notfall_beenden(me, b)` – Beenden (Administrator).
- `notfall_ende(wer, einstellungenZurueck, notiz)` – Gemeinsamer Abschluss (auch für das Server-Werkzeug deploy/notfall-aus.php, das denselben Ablauf ohne API nachbildet)
- `notfall_benachrichtigen(titel, facts)` – Sofortige Benachrichtigung nach der Antwort – ohne Bündelpause, auch wenn das Ereignis ausgeschaltet ist, solange Empfänger eingetragen sind (ein Notfall …

## `app/api/lib/nutzer.php`

_Mitarbeiter-Zugänge und Passwortregeln_

**Nutzer**

- `users_load()` – Nutzerliste; bisherige Einzel-Passwort-Installation wird einmalig zum Nutzer „admin“
- `users_save(users)`
- `user_find(users, id)`
- `nutzer_hat_zugang(u)` – Mitarbeiter ohne Anmeldung (z. B. Lager): gehört zur Mitarbeiterliste (Urlaubsplanung), kann sich aber nicht anmelden – immer deaktiviert, unbrauchbares …
- `user_public(u)`
- `nutzer_vertreter(v, alt)` – Vertreter eines Mitarbeiters (Feld „vertreter“, CRM „Mein Cockpit“: seine Kunden = Vertreter oder Vertreter 2): Nummer aus Stammdaten → Vertreter oder leer.
- `setup_allowed()` – Ersteinrichtung im Browser nur auf einem wirklich leeren System – nie, wenn Nutzerdaten vorhanden, aber nicht lesbar sind, und nie auf dem Produktivserver …
- `dummy_kosten(hashes)`
- `dummy_verify(pw, hashes)`
- `anmeldung_angleichen()`
- `login_failure(u)`
- `ghost_lock(scope, name, fail, neu)` – Fehlversuche für unbekannte Benutzernamen wie bei echten Zugängen zählen: gleiche Sperrmeldung nach gleich vielen Versuchen, damit die Antwort nicht verrät, …
- `active_admins(users)`
- `nutzer_deaktivieren(me, id, grund)` – Zugang eines Mitarbeiters deaktivieren (Modul Sicherheit → ungenutzte Konten; gleiche Wirkung wie „aktiv“ abwählen in Verwaltung → Mitarbeiter): nicht der …
- `benutzername_vorschlag(vorname, nachname, belegt)` – Benutzername aus Vor- und Nachname: „vorname-nachname“, klein, Umlaute als ae/oe/ue/ss, Akzente ohne Zeichen, Leerzeichen und Sonderzeichen werden zu „-“; …
- `mitarbeiter_ohne_zugang_anlegen(vorname, nachname, me)` – Mitarbeiter ohne Anmeldung anlegen (Schnittstelle für Module, z. B. HR-Übernahme der Urlaubsplanung).
- `nutzer_person(b, neu)` – Name, Vorname, Nachname und E-Mail eines Nutzers aus der Anfrage.
- `clean_username(v)`
- `check_password(pw, username)`
- `pw_datenleck(pw)`
- `pw_datenleck_vorab(pw)` – Vorab (vor dem Sperren der Nutzer-/Kundendaten) prüfen, damit die Anfrage beim Dienst keine anderen Anmeldungen aufhält
- `pw_datenleck_status(ok)` – Letztes Ergebnis merken (Konfigurationsprüfung zeigt, ob der Dienst erreichbar war); Fehler stören nicht
- `pw_leak_bei_anmeldung(pw, acc, merker)` – Bei der Anmeldung: bestehendes Passwort einmal je Passwort prüfen (Merker = Prüfwert des gespeicherten Hashes).
- `mail_tpl_nutzer(u, startPw, note)` – E-Mail an einen Mitarbeiter mit seinen Zugangsdaten (Verwaltung → Nutzer).

## `app/api/lib/oidc.php`

_Mitarbeiteranmeldung über Keycloak (ADR-003, GR-110) – Roadmap 7b, vorerst nur in CI und lokaler Testumgebung._

- `oidc_modus()`
- `alter_zugang_aus()` – Bisheriger Eingabebereich mit eigener Anmeldung (angebot-stafl.de/admin/) stillgelegt (Entscheidung Inhaber 23.10.2026): WA_EIGENE_ANMELDUNG=aus (Betrieb: …
- `eigene_anmeldung_stillgelegt()` – Gilt für diese Anfrage: Host ohne zentrale Anmeldung und alter Zugang aus
- `eingabe_adresse()` – Neuer Eingabebereich (Hinweis, Weiterleitung, Verweise in Mails) – nur https-Adressen
- `oidc_einstellung(name)` – Einstellung des Webservers (SetEnv) bzw. des Prozesses – nie aus Kopfzeilen (die heißen HTTP_…)
- `oidc_identitaet()` – Vom Webserver geprüfte Identität oder null
- `oidc_zweiter_faktor(id)` – Anmeldestärke: Den zweiten Faktor verlangen wir nur von Konten, für die er vorgeschrieben ist: Administratoren immer, übrige nach Sicherheitseinstellung bzw. …
- `oidc_stufe_ok(id, u)`
- `oidc_stufe_adresse()` – Anmeldung mit zweitem Faktor bei Keycloak anfordern (zweite Stufe; fehlt er, richtet der Mitarbeiter ihn dort ein)
- `oidc_konto(id)` – Mitarbeiterkonto zur Identität; ohne aktives Konto 403 (nicht 401 – sonst meldete der Browser sich endlos neu an)
- `oidc_aktiv(u)`
- `oidc_geloescht()` – Kennungen (sub) der Keycloak-Konten gelöschter Mitarbeiter → Zeitpunkt (Dokument „oidc-geloescht“, nur wachsend und klein).
- `oidc_geloescht_merken(sub)`
- `oidc_nutzer()` – Angemeldeter Mitarbeiter auf einem Keycloak-Host.

**Leerlauf über alle Adressen (seit 04.11.2026)**

- `oidc_aktiv_schluessel(id)`
- `oidc_aktivitaet()`
- `oidc_leerlauf(id)` – Abgelaufen?
- `oidc_aktivitaet_merken(id)`
- `oidc_anmeldung_merken(u, authTime)` – Letzte Anmeldung am Mitarbeiterkonto (lastLogin) = Anmeldezeitpunkt bei Keycloak (auth_time) – für „letzte Anmeldung“ und ungenutzte Konten (Modul Sicherheit).

**Ablauf und Beenden von Sitzungen auf Keycloak-Hosts**

- `oidc_abmeldungen()`
- `oidc_abmeldung_merken(sids, uids)` – Beendete Sitzungen vermerken (Keycloak-sid bzw. Mitarbeiter-Kennungen)
- `oidc_ende_zeit(id, u)` – Zeitpunkt, bis zu dem eine Anmeldung bei Keycloak nicht mehr genügt, und Grund ('inaktiv' \| 'beendet'); 0 = keiner
- `oidc_erneuern(u, grund, ende, authTime)` – Erneute Anmeldung bei Keycloak verlangen; Schutz vor Endlosschleifen wie bei der zweiten Stufe (3 in 10 Minuten)
- `oidc_sitzung_vermerken(regSid, kcSid)` – Keycloak-Sitzung (sid) am Eintrag im Sitzungsregister vermerken – für „Sitzung beenden“
- `oidc_gesehen()` – Sitzungsregister aktuell halten (Anzeige „zuletzt aktiv“, Adresse) – wie bei der bisherigen Anmeldung
- `oidc_abmelde_adresse()` – Abmelden auf einem Keycloak-Host: eigene Sitzung beenden; der Browser meldet sich danach über das Modul bei Keycloak ab (beendet die zentrale Sitzung, …
- `oidc_neu_anmelden_adresse()` – Erneute Anmeldung bei Keycloak statt eigener Passwortabfrage (ADR-003: max_age=0).
- `oidc_neu_anmelden()`

## `app/api/lib/passkey.php`

_Passkeys (WebAuthn) für Mitarbeiter-Zugänge – ohne Fremdbibliothek._

- `b64u_enc(bin)`
- `b64u_dec(s)`
- `has_passkeys(u)`
- `has_second_factor(u)` – Zweiter Faktor vorhanden: Authenticator-App oder mindestens ein Passkey
- `passkey_ref(pk)` – Kurzer Verweis für die Oberfläche (statt der Credential-ID)
- `passkey_public(u)`
- `passkey_host()` – Relying Party = aufgerufener Host ohne Port (keine IP-Adressen – WebAuthn erlaubt sie nicht)
- `passkey_rp_id()`
- `passkey_origin()`

**Minimaler CBOR-Leser (RFC 8949): Zahlen, Byte-/Textfolgen, Listen, Maps, einfache Werte**

- `cbor_decode(data, pos, depth)`
- `cbor_need(data, pos, n)`
- `cbor_half(h)`

**Schlüssel: COSE → PEM**

- `der_len(n)`
- `der(tag, body)`
- `der_uint(bin)`
- `pem_public(spki)`
- `cose_to_pem(k)` – Liefert [alg, PEM]; nur ES256 (P-256) und RS256

**Authenticator-Daten**

- `passkey_auth_data(ad, attested)` – Prüft rpIdHash und die Flags UP + UV; mit $attested zusätzlich AT und liest Credential-ID und Schlüssel
- `passkey_client_data(raw, type, challenge)` – clientDataJSON: Art, Anfrage (Challenge) und Herkunft prüfen
- `passkey_challenge(kind, extra)` – Neue Anfrage (Challenge) in der Sitzung ablegen: $kind = 'pkReg' \| 'pkAuth'
- `passkey_take(kind)` – Anfrage einmalig entnehmen (gilt 5 Minuten)
- `passkey_create_options(u, challenge)` – Optionen für navigator.credentials.create()
- `passkey_verify_registration(b, challenge)` – Registrierung prüfen; liefert den zu speichernden Eintrag (ohne Name)
- `passkey_signature_ok(pk, authData, clientDataRaw, sig)` – Signatur einer Anmeldung prüfen (Daten bereits auf Herkunft/Challenge geprüft)
- `passkey_get_options(challenge, u)` – Optionen für navigator.credentials.get(); ohne Nutzer: auffindbare Schlüssel (leere allowCredentials)
- `passkey_name(v, u)` – Name eines Passkeys (Vorgabe „Passkey N“)

## `app/api/lib/pdf.php`

_Schlanker PDF-Erzeuger (ohne Fremdbibliothek)_

- `__construct(w, h)`
- `addPage()`
- `pageCount()`
- `enc(s)` – UTF-8 → Windows-1252 (nicht darstellbare Zeichen werden „?“)
- `width(s, size, bold)`
- `wrap(s, size, max, bold)` – Zeilenumbruch nach Wörtern; zu lange Wörter werden hart getrennt
- `esc(t)`
- `col(hex)`
- `y(y)`
- `text(x, y, s, size, bold, color, align)` – Text an Grundlinie y; align: l, r (x = rechter Rand)
- `rect(x, y, w, h, fill)`
- `line(x1, y1, x2, y2, lw, color)`
- `jpeg(file, x, y, w)` – JPEG einbinden (Breite in pt; Höhe aus dem Seitenverhältnis); liefert die Höhe
- `output(title)`

## `app/api/lib/protokoll.php`

_Protokoll, Änderungstexte, Anmeldeversuche_

**Protokoll**

- `protokoll_grenze(jetzt)` – Ältester aufbewahrter Monat (JJJJ-MM): laufender Monat minus PROTOKOLL_MONATE
- `protokoll_monate()` – Monate des Protokolls, die aufbewahrt werden (neueste zuerst) – Protokollansicht bietet nur diese an
- `protokoll_aufraeumen()` – Monatsdokumente vor der Grenze löschen; liefert die entfernten Monate (aufsteigend).
- `audit(a, s, d, who, merge)`
- `price_text(p)`
- `sale_text(sale)`
- `variant_text(v, oid)`
- `alts_text(alts)`
- `changes_between(a, b)` – Änderungen zwischen zwei Ständen als Liste {k, code, name, f, from, to}
- `changes_merge(old, new)` – Neue Änderungen in einen bestehenden Eintrag einarbeiten: Ausgangswert bleibt, Endwert wird aktualisiert
- `changes_summary(d)`
- `proxy_adressen_merken(name, adr, familie)` – Zuletzt aufgelöste Adressen eines Proxy-Namens (im Datenordner, sonst im Temp-Ordner; nur vom Server selbst geschrieben, getrennt nach IPv4/IPv6).
- `trusted_proxy(ip)`
- `client_ip()`
- `client_key()` – Schlüssel für Fehlversuche: IPv4 je Adresse, IPv6 je /64-Netz (ein Anschluss hat meist ein ganzes /64 – sonst könnte man durch Wechseln der Adresse beliebig …
- `attempts_key(bereich)` – Bereiche: 'mitarbeiter' (Anmeldung im Eingabebereich), 'kunde' (Kunden-Login mit Passwort), 'kundelink' (Links aus Kunden-E-Mails: ein schon benutzter oder …
- `attempts_wer(name)`
- `attempts_check(bereich)`
- `attempts_record(ok, bereich, name)` – $name: Benutzername des Versuchs ('' = ohne Namen, z. B. Einmal-Links – wird nie durch eine Anmeldung zurückgenommen)

## `app/api/lib/rechte.php`

_Nutzerrechte: was eine Rolle bzw. ein einzelner Nutzer im Eingabebereich sehen und tun darf._

**Rechtekatalog: PERMS + Modulzugang je Kachel**

- `perms_katalog()`
- `recht_modul(key)` – Modul eines Rechts: Zuordnung aus regeln/berechtigungen.toml (erzeugt: RECHTE_MODUL), sonst Präfix „<modul>.“

**Rollen**

- `rollen_dok(neu)`
- `rollen_eigene()`
- `rolle_existiert(id)`
- `rolle_name(id)`
- `user_rollen(u)` – Alle Rollen eines Mitarbeiters (bekannte, ohne Doppelte); Administrator nur als Hauptrolle
- `rollen_text(u)`
- `rights_roles()` – Rechte je Rolle (Standardrollen gespeichert oder Standard, dazu die eigenen Rollen).
- `rights_clean(list)`
- `rights_close(perms)` – Voraussetzungen ergänzen (wer bearbeiten darf, darf auch sehen)
- `user_perms(u, roles)` – Wirksame Rechte eines Nutzers: alle Rollen + erlaubt − verboten (Administrator: alle)
- `may(u, perm)`
- `require_perm(perm, write)`
- `require_perm_confirmed(perm, key)` – Wie require_admin_confirmation, aber für ein Recht statt der Administratorrolle.

**Modulzugang durchsetzen (GR-103: serverseitig, nicht über die Kachel)**

- `modul_zugang_frei(u, modul, perms)`
- `require_modulzugang(modul, write)` – Angemeldet UND Modulzugang „<modul>.zugang“ – unabhängig vom Host der Anfrage (GR-103).
- `modul_host_frei(u, modul)`
- `anfrage_modul(aktion)` – Modul der Oberfläche dieser Anfrage: der Host (Webserver: WA_OBERFLAECHE, nie aus Kopfzeilen) – sonst die Oberfläche der Aktion, außer dem gemeinsamen …
- `modul_zugang_durchsetzen(aktion)`
- `rights_catalog()`
- `rollen_liste(roles, users)` – Rollenübersicht für die Verwaltung (Administrator): Rechte, Name, Anzahl Mitarbeiter
- `rechte_module()` – Module für die Rechte-Übersicht: Kachel-Module in Dashboard-Reihenfolge, dazu „plattform“ für Rechte ohne Modul

## `app/api/lib/sicherheit.php`

_Sicherheitseinstellungen, Länder-/IP-Sperre, Zwei-Faktor, Sitzungsregister, Wartungsmodus_

**Sicherheitseinstellungen**

- `bestaetigung_noetig(key)`
- `bestaetigung_sekunden()` – Wie lange eine Passwortbestätigung gilt (Sekunden)
- `bestaetigung_katalog()`
- `sec()`
- `geo_land_unbekannt(ip)` – Öffentliche Adresse, für die die Länderdatenbank kein Land kennt (interne Adressen und fehlende Datenbank: false)
- `geo_blocked(ip, S)` – Ländersperre: Land, wegen dem diese Adresse nach den Einstellungen $S gesperrt ist (ISO-Code, GEO_UNBEKANNT = ohne erkennbares Land), sonst null.
- `geo_count(cc)`
- `ip_in(ip, cidr)`
- `ip_allowed(ip, list)`
- `valid_cidr(c)`
- `twofa_required(u)` – Pflicht zum zweiten Faktor: nach Sicherheitseinstellung (off\|admins\|all) oder einzeln vom Administrator gesetzt (Nutzerfeld twofaPflicht, optional – fehlt …
- `is_https()`

**Zwei-Faktor (TOTP, RFC 6238)**

- `b32_encode(bin)`
- `b32_decode(s)`
- `totp_at(secret, step)`
- `totp_check(secret, code, last)` – Liefert den verwendeten Zeitschritt oder null; jeder Code gilt nur einmal
- `recovery_codes()`
- `rc_hash(c)`

**Sitzungsregister**

- `sess_prune(list)`
- `sess_register(u)`
- `sess_remove(match)`

**Wartungsmodus**

- `wartung()` – Wirksame Wartung der Angebotsseite: im Notfallmodus (lib/notfall.php) immer – mit dessen neutralem Kundenhinweis, ohne Urheber („notfall“ = true) –, sonst …
- `wartung_gespeichert()` – Von Hand eingeschaltete Wartung (Dokument „wartung“) – unabhängig vom Notfallmodus, bleibt nach dessen Ende bestehen
- `sec_clean(b, old, me)` – Sicherheitseinstellungen prüfen und vollständig zurückgeben (Speichern, Vorlagen, Import) – $me = handelnder Administrator

## `app/api/lib/sitzung.php`

_Mitarbeiter-Sitzung, Rollen, Passwortbestätigung, CSRF_

**Sitzung**

- `app_client()` – App-Zugriff (docs/app-api.md): Die App sendet „X-WA-Client: app“ und trägt die Sitzungskennung in der Kopfzeile „X-WA-Sitzung“ statt in einem Cookie; jede …
- `app_session_header()`
- `sitzung_cookie_name()`
- `start_session()`
- `bg_request()` – Automatische Abfragen im Hintergrund (Abgleich mit anderen Bearbeitern) zählen nicht als Aktivität – die Abmeldung nach Inaktivität bleibt wirksam.
- `current_user()`
- `require_auth(write, role)`
- `sign_in(u)`
- `me_payload(u)`
- `user_update(id, fn)` – Nutzer innerhalb der Sperre ändern und speichern
- `mark_admin_confirmed(u)`
- `confirmation_locked(u)`
- `require_admin_confirmation(key)` – $key: Aktion im Katalog BESTAETIGUNG (lib/sicherheit.php) – ist die Bestätigung abgeschaltet, genügt die Administrator-Anmeldung
- `confirm_password(me, password, invalidStatus)` – Gemeinsame, kontoweite Bremse für Passwortbestätigungen; nie durch neue Sitzungen zurücksetzen.
- `keep_current_session(u)` – Nach Änderungen am zweiten Faktor nur die bestätigende Sitzung behalten.
- `require_csrf()`

## `app/api/mail.php`

_E-Mail-Versand über einen SMTP-Server (z._

- `env_str(k)`

**Verschlüsselung des gespeicherten Postfach-Passworts**

- `mail_key(create)`
- `mail_encrypt(plain)`
- `mail_decrypt(enc)`
- `mail_account(konto)`
- `mail_cfg_aus_konto(a, source)` – Versanddaten aus einem gespeicherten Postfach (Passwort entschlüsselt; passError, wenn das nicht geht)
- `mail_konto_view(a)` – Anzeige eines gespeicherten Postfachs für die Verwaltung – nie das Passwort, nur ob eines gespeichert ist
- `mail_cfg_intern()` – Versand für interne E-Mails (nur an Mitarbeiter): eigenes Postfach, sonst das Kunden-Postfach (oder null)
- `mail_cfg()` – Mail-Konfiguration oder null, wenn der Versand nicht eingerichtet ist
- `mail_base_url()` – Basisadresse der Angebotsseite für Links in E-Mails – nie aus dem Host-Header der Anfrage
- `mail_clean_header(s)`
- `mail_enc_header(s)`
- `mail_addr(email, name)`
- `mail_build(cfg, to, toName, subject, text, html, extra, anhaenge)` – Vollständige Nachricht (Text + HTML), optional mit Anhängen [{name, type, data, cid?}] (dann multipart/mixed); mit 'cid' eingebettet (multipart/related, im …
- `__construct(cfg)`
- `err(m)`
- `read()`
- `cmd(c, ok, what)`
- `ctx()`
- `open()`
- `connect()`
- `send(to, message)`
- `close()`

**Vorlagen**

- `mail_h(s)`
- `mail_layout(title, bodyHtml, signature, footer, footHtml)`
- `mail_layout_einladung(title, bereich, ueberschrift, bodyHtml, signature, footer, schritte)` – Einladungen und Passwort-Links: gleiche Farben wie mail_layout, dazu dunkles Kopfband, große Überschrift, hervorgehobener Knopf und kurze Schritte.
- `mail_button_gross(url, label)` – Großer Knopf (Einladung): volle Breite auf schmalen Bildschirmen über max-width, sonst so breit wie der Text
- `mail_feld(label, wert)` – Hervorgehobene Angabe (z. B. Benutzerkennung)
- `mail_button(url, label)`
- `mail_greeting(c)`

## `app/api/storage.php`

_Shared persistence for HTTP and maintenance tools._

- `store_path(name)`
- `store_mode()`
- `store_db()`
- `store_sql(name)`
- `store_read(name)`
- `store_write(name, data)`
- `store_delete(name)`
- `store_mtime(name)`
- `store_names(prefix)`
- `store_commit()`
- `store_rollback()`
- `with_lock(name, fn)`
- `store_stats()` – Kennzahlen für die Übersicht im Eingabebereich

## `app/assets/admin-rollen.js`

_Wochenangebot – Eingabebereich, Verwaltung → Rollen und Rechte (nur Administratoren) Eigene Rollen anlegen, umbenennen, kopieren und löschen; je Rolle und Modul eine Stufe (Kein Zugang · Ansehen · Bearbeiten · Voll), …_

**Module und Stufen**

- `stufeVon(set, mid)` – Stufe eines Moduls aus einer Rechteliste; „angepasst“, wenn sie keiner Stufe entspricht (sensible Rechte zählen nicht), „nurzugang“, wenn nur die Kachel …
- `stufeSetzen(mid, st)`

**Entwurf**

- `neuerEntwurf(id, kopie)`
- `aenderungen()`

**Bausteine**

- `stufenHTML(m, gross)`
- `listeHTML()`
- `kopfHTML()`
- `blickHTML(aktiv)`
- `zeilenHTML(aktiv)`
- `rechtHTML(p, m)` – Ein Recht: Schalter, Bezeichnung, Erklärung (falls im Katalog), Voraussetzung, Vorschau-Bild
- `detailHTML(m)`

**Rollen vergleichen**

- `vergleichHTML()`

**Zeichnen**

- `aktivesModul()`
- `zeichnen()`
- `neuZeichnen(fokus, ersatz)` – Neu zeichnen und den Fokus auf dem bedienten Element halten (Tastatur, Bildschirmleser)
- `standAktualisieren()`
- `weiterOhneSpeichern()`
- `laden(id)`

## `app/assets/detailkarte.js`

_STAFL-Plattform – Detailkarte (Straßen, Gebäude, Ortsnamen) vom eigenen Server Gemeinsame Kartenkomponente für die CRM-Karte und die Auswertung der Verwaltung._

- `webgl()`
- `verfuegbar()` – Kartendatei vorhanden?
- `skript(src)`
- `laden()`
- `stil(art)`
- `geojson(punkte)`
- `erstellen(el, opt)`

## `app/assets/format.js`

_Zahlen, Beträge, Mengen, Prozente und Datum – EIN Format für alle Seiten der Plattform (Auftrag des Inhabers 02.11.2026_

- `nf(min, max)`
- `wert(v)`
- `runden(n, stellen)` – Kaufmännisch runden wie der Server (PHP round): 12,345 → 12,35, auch wenn die Binärzahl knapp darunter liegt
- `zahl(v, min, max)` – Zahl mit min…max Nachkommastellen, echtes Minus; -0 wird 0
- `mitEinheit(s, einheit)`
- `euro(v)`
- `euroKachel(v)`
- `euroKg(v)`
- `kg(v)`
- `kgSumme(v)`
- `prozent(anteil)` – Anteil als Bruch (0,123 → 12,3 %)
- `vorzeichen(n, s)`
- `veraenderung(anteil)` – Veränderung als Bruch (0,123 → +12,3 %)
- `pp(anteil)` – Differenz zweier Anteile in Prozentpunkten (0,012 → +1,2 Pp)
- `differenz(v, einheit, min, max)` – Differenz mit Vorzeichen in einer Einheit (z. B. Preisänderung: +0,50 €/kg)
- `alsDatum(d)`
- `datum(d)`
- `datumZeit(d)`
- `kw(woche, jahr)`

## `app/assets/theme.js`

_Hell/Dunkel-Einstellung vor dem ersten Zeichnen anwenden (ohne Inline-Skript, wegen Content-Security-Policy)_

- `lesen(k)`
- `schreiben(k, v)`
- `softwareGrafik()` – Zeichnet der Browser ohne Grafikkarte?
- `automatisch()`
- `anwenden()`
- `zaehlt(d, t)`
- `zeigen()`
- `frei(d)` – Gespeichert: Seiten, deren Fenster nach erfolgreichem Speichern offen bleibt, melden das (STAFL_FENSTER.gespeichert); Abschicken allein zählt nicht – schlägt …
- `oben()`
- `start()`
- `lokal(wert)`
- `setzen(wert)`
- `merken(wert)`
- `pruefen(el)`
- `anmelden()`
- `start()`

## `deploy/anmeldung/theme/stafl/login/resources/js/stafl-otp.js`

_STAFL-Plattform – Einmalcode-Felder der Anmeldeseite (Felder mit data-stafl-otp_

- `nurZiffern(wert)`
- `bereinigen(feld)`
- `einrichten(feld)`
- `einmalAbsenden(form)` – Jedes Anmeldeformular nur einmal absenden.
- `freigeben()`
- `start()`

## `deploy/bereitstellen.py`

_Bereitstellung eines Stands_

- `version(inhalt)`
- `ausgeliefert(rel)` – Gehört die Datei (Pfad unter app/) zur Prüfliste?
- `ist_seite(rel)`
- `ziel(seite, pfad)` – Pfad einer Einbindung relativ zu app/ (wie im Browser aufgelöst).
- `stempeln(seite, inhalt, dateien, fehlend)` – HTML-Seite mit Versionsnummern aus dem Inhalt der eingebundenen Dateien (fehlt eine Datei: ohne Nummer).
- `ersetzen(m)`
- `ohne_versionen(inhalt)`
- `bereitstellung(dateien)` – dateien: Pfad unter app/ → Inhalt (wie im Commit).
- `zusatz_seiten(dateien, zusatz)` – Seiten des Dashboards stempeln. zusatz: Pfad unter dashboard/ → Inhalt; Einbindungen werden wie im Browser aufgelöst (/dashboard/ liegt neben app/: …
- `php_text(s)`
- `liste_php(liste, quelle)`
- `schreiben(pfad, inhalt, modus)` – Atomar ersetzen (Apache liest nie eine halb geschriebene Datei); lesbar für den Webserver.
- `lesen(pfad)`

**Quelle: Git-Objekte des Commits (Server)**

- `git(*args, eingabe)`
- `commit_dateien(commit, ordner)` – Pfad unter <ordner>/ → Inhalt aller normalen Dateien des Commits (ohne Verweise und Untermodule).
- `server(nur_pruefen)`

**Quelle: Ordner (Testkopie, CI-Prüfung)**

- `ordner_dateien(app)`
- `verzeichnis(app, quelle)` – Kopie eines app/-Ordners bereitstellen: Seiten stempeln, Prüfliste schreiben (wie auf dem Server).
- `zusatz_verzeichnis(app)` – Im Testlauf unter app/dashboard/ eingeblendetes Dashboard (tests/run_e2e.py, ZUSATZ) wie auf dem Server stempeln.
- `main(argv)`

## `deploy/datenbank.py`

_Offline migration/rollback and online SQLite backup._

- `document_path(relative)` – True for a data file that belongs in the database: not a dot path, geo/, index.php or a sidecar.
- `documents(root)`
- `validate(db)`
- `connect(root)`
- `migrate(root)`
- `rollback(root)`
- `legacy_files(root)` – Old data files after the switch to SQLite: same selection as documents(), never read by the application.
- `_sha(p)`
- `legacy(root, archive)` – List old data files or move them into a checked archive (never deletes before the archive is verified).
- `snapshot(root, target)`
- `main()`

## `deploy/karte/adressen.py`

_Adressverzeichnis für die CRM-Karte aus OpenStreetMap (ODbL)_

- `norm_text(s)` – Kleinbuchstaben, Umlaute ausgeschrieben, nur a–z und 0–9 (für Orte).
- `norm_strasse(s)` – Wie norm_text, „str.“/„str“ am Wortende wird „strasse“ (Hauptstr. = Hauptstraße = Haupt-Straße).
- `norm_nr(s)` – Hausnummer: Kleinbuchstaben ohne Leerzeichen, nur Ziffern, Buchstaben, - und / (12 A → 12a).
- `norm_plz(s)`
- `nummern(roh)` – Mehrere Hausnummern an einem Objekt („12;14“, „12, 14“) einzeln; Bereiche („12-14“) bleiben ganz.
- `__init__(arbeit)`
- `schluessel(tags)` – (plz, ort, strasse, [nummern]) aus den addr:*-Angaben oder None (ohne Straße bzw. ohne PLZ und Ort).
- `punkt(k, lat, lon)`
- `weg(k, n0, n1)`
- `knoten(i, lat, lon)`
- `fertig(ziel, quelle)`
- `aus_osm(quelle, z)` – Zwei Durchläufe über die OSM-Datei (pyosmium); Filter laufen in C++, Python sieht nur Adressen und deren Eckpunkte.
- `aus_json(quelle, z)` – Testdaten: Liste von {strasse, nr, plz, ort, lat, lon} (wie addr:* in OpenStreetMap).
- `main(argv)`

## `tests/deploy/github_stub.py`

_Minimaler Ersatz für die GitHub-API im Deploy-Test: liefert Release- und CI-Läufe aus einer Zustandsdatei._

- `log_message(*a)`
- `do_GET()`

## `tests/deploy/test_cdn.py`

_bunny.net vor dem Server (Caddyfile, Abschnitt „cdn“) mit echtem Caddy in der Fassung des Betriebs._

- `check(name, ok, info)`

**statisch**

**Verhalten mit echtem Caddy**

- `docker(*args, pruefen)`
- `caddy_start(kennung, umgebung, netzwerk, port)`
- `ip(name)`
- `abruf(ziel, pfad, kopf)` – Abruf aus dem Besucher-Container (öffentliche Adresse): (Status, Antwortköpfe, Inhalt).
- `vom_server(kopf)`

## `tests/deploy/test_dashboard_domains.py`

_Dashboard-Hosts: Modul-Hosts bleiben 503-Platzhalter bis zur Freigabe (GR-105); die Hosts der zentralen Anmeldung (ADR-003, Inbetriebnahme Schritt 6) führen nur zu Zielen, die es ausschließlich mit der …_

- `site(kopf)`

## `tests/deploy/test_datenbank.py`

_Real PHP/SQLite, independent SQL inspection, migration failure and restore tests._

- `check(name, condition)`
- `command(root, action, *args)`
- `php(root, code)`

## `tests/deploy/test_images.py`

_Container-Images fest über Digest (Sicherheitsdurchsicht 26.10.2026, Befund 12): jedes fremde Image in den Compose-Dateien und im Dockerfile ist mit @sha256 festgelegt – ein Release holt so nie unbemerkt eine andere …_

- `images(pfad)`

## `tests/deploy/test_zwischenspeichern.py`

_Browser-Zwischenspeicher (Caddyfile, Abschnitt „zwischenspeichern“) mit echtem Caddy in der Fassung des Betriebs._

- `check(name, ok, info)`
- `bloecke()` – Kopfzeile → Inhalt aller Blöcke der obersten Ebene (Sites und Abschnitte).

**statisch: Abschnitt und Zuordnung**

- `import_von(kopf)`

**Verhalten mit echtem Caddy**

- `redirect_request(*a, **k)`
- `hostport(p)`
- `abruf(basis, pfad, kopf)`

## `tests/e2e/auth_helpers.py`

_HTTP-Client und Zeitsteuerung ausschließlich für isolierte Testdaten/Sitzungen._

- `__init__(ip)`
- `call(action, data, csrf)`
- `login(username, password)`
- `expire()`
- `expire_session(sid)`
- `read_users()`
- `expire_confirmation_lock()`

## `tests/e2e/kunden_hilfe.py`

_HTTP-Client mit eigener Sitzung für API-Tests (IP über X-Forwarded-For, wie hinter dem eigenen Proxy)._

- `__init__(ip)`
- `call(action, data, raw)`

## `tests/e2e/smtp_test.py`

_Kleiner Test-Mailserver für die Ende-zu-Ende-Tests (nimmt Nachrichten an und hält sie im Speicher)._

- `__init__(port, user, password, mode, cert, key)`
- `_loop()`
- `_session(c)`
- `close()`

## `tests/e2e/test_admin_confirmation.py`

_Sensible Aktionen, kontoweite Bestätigungsbremse und Dateisperren über echte HTTP-Anfragen._

- `check(name, condition)`
- `snapshot()`

## `tests/e2e/test_admin_confirmation_ui.py`

_Abgelaufene Admin-Freigabe im Browser_

- `check(name, value, info)`
- `sicherheit()`

## `tests/e2e/test_aktionsregister.py`

_Aktionsregister (regeln/aktionen/*.toml → app/api/lib/aktionen-liste.php) wirkt im API-Einstieg für jede Aktion._

- `check(n, c, i)`
- `anfrage(action, methode, typ, daten)`

## `tests/e2e/test_anmeldebremse.py`

_Fehlversuchsbremse je Adresse (lib/protokoll.php), Abmelden mit CSRF und Bedrohungsliste ohne Nebenwirkung beim Lesen. - Eine erfolgreiche Anmeldung nimmt nur die Fehlversuche für denselben Namen zurück (eigene …_

- `doc(name)`
- `check(n, c, i)`

## `tests/e2e/test_anmeldeseite.py`

_Testgruppe anmeldeseite_

- `check(n, c, i)`
- `sicherheit(**w)`
- `pruefen(ip, kopf)`

## `tests/e2e/test_auth_hardening.py`

_Direkte HTTP-Regressionen_

- `check(name, condition)`
- `__init__(ip)`
- `call(action, data)`
- `login()`
- `code(secret)`

## `tests/e2e/test_benachrichtigung.py`

_Benachrichtigungen an Mitarbeiter_

- `check(n, c, i)`
- `doc(name)`
- `mails_to(addr)`

## `tests/e2e/test_bestaetigung.py`

_Sicherheit (Modul) → Einstellungen → Passwortbestätigung: je Aktion einstellbar, ob das Passwort verlangt wird; feste Aktionen (Zugänge, Rechte, Sicherheit, Postfach) immer mit Bestätigung; Gültigkeitsdauer …_

- `check(n, c, i)`
- `bestaetigt_vor(cl, sekunden)` – Passwortbestätigung dieser Sitzung auf „vor <sekunden> Sekunden“ setzen (simulierter Zeitablauf).
- `sec_doc()`

## `tests/e2e/test_einheit.py`

_Einheitliches Erscheinungsbild aller Mitarbeiter-Oberflächen (Dashboard, Eingabebereich auf den Bereichs-Hosts Angebot, Verwaltung, Bestand, alle Modulseiten – HR, CRM, Controlling, Leergut, Marketing, QS, REWE, …_

- `check(n, c, i)`
- `neue_seite(breite, dunkel)`
- `als_bereich(pg, bereich)`
- `umleiten(route)`

## `tests/e2e/test_geo.py`

_Testgruppe geo: Ländersperre im Modul Sicherheit (Einstellungen → Ländersperre, Dialog) – Länderliste nach Kontinenten, Schnellauswahl (Kontinente, EU, EWR, DACH, Nachbarn, NATO, G7, BRICS), Suche, …_

- `check(n, c, i)`
- `login(pg, user, pw)`
- `post(pg, action, body, headers)`
- `get(pg, action, headers)`
- `settings(pg)`
- `geo_dialog(pg)`
- `ja(pg)`

## `tests/e2e/test_geo_ip.py`

_Testgruppe geo_ip: IP-Suche der Ländersperre (Modul Sicherheit, Dialog Ländersperre) – IPv4/IPv6 einem Land zuordnen, Hinweise, nur für Administratoren._

- `check(n, c, i)`

## `tests/e2e/test_geraete.py`

_Vertraute Geräte: Ein Browser, auf dem sich ein Zugang schon erfolgreich angemeldet hat, kommt auch während einer fremd ausgelösten Kontosperre mit dem richtigen Passwort durch (Mitarbeiter mit und ohne Zwei-Faktor, …_

- `check(n, c, i)`
- `doc(name)`
- `totp(secret, step)`
- `jar(c)`
- `kennung(c)`
- `gleicher_browser(c, ip)` – Neuer Client (neue Sitzung, andere Adresse) mit der Gerätekennung des Browsers c – wie nach dem Schließen des Browsers
- `mit_kennung(c, wert, ip)`
- `nutzer(name)`
- `nutzer_setzen(name, **kw)`
- `kunde(uname)`
- `kunde_setzen(uname, **kw)`
- `versuche(name, n, netz, aktion)`

**Mitarbeiter ohne zweiten Faktor**

**Mitarbeiter mit Authenticator-App**

**Administrator: Meldung bei neuem Gerät**

- `meldungen()`

## `tests/e2e/test_herkunft.py`

_Herkunftsprüfung im API-Einstieg (GR-109, lib/herkunft.php): nur Anfragen von der eigenen Seite. `Sec-Fetch-Site` same-site/cross-site → 403 (auch von Nachbar-Subdomains wie test.angebot-stafl.de); bei Anfragen außer …_

- `check(n, c, i)`
- `mit(cl, **kopf)` – Kopfzeilen für die nächsten Anfragen des Clients setzen (None entfernt).
- `roh(action, method, kopf, daten)`
- `do_GET()`
- `log_message(*a)`

## `tests/e2e/test_integritaet.py`

_Dateiprüfung (Sicherheit → Dateiprüfung)_

- `check(n, c, i)`
- `doc(name)`
- `run(c)`
- `by_path(r)`
- `mails(word)`

## `tests/e2e/test_mail_intern.py`

_Postfach für interne E-Mails (z._

- `check(n, c, i)`
- `neu(server, n0)`

## `tests/e2e/test_mhd_mail.py`

_Bestand → „MHD an Verkauf“: die MHD-Liste (Suche „MHD“: kürzestes MHD bis heute + 14 Tage) per E-Mail an die Empfänger der Benachrichtigung „MHD-Liste an den Verkauf“ – Bild der Liste eingebettet (cid), Excel-Datei …_

- `check(n, c, i)`
- `png(w, h)` – Kleines gültiges PNG (weiß) ohne Zusatzbibliotheken.
- `chunk(t, d)`
- `teil(msg, typ)`

**Rechte und Prüfungen**

**Versand**

**Oberfläche**

- `anmelden(page, user, pw)`

## `tests/e2e/test_modul_wartung.py`

_Wartung je Oberfläche (GR-107)_

- `check(n, c, i)`
- `eingabe(cl)`
- `kopf(cl, action)` – Kopfzeilen einer Antwort mit der Sitzung des Clients (auch bei Fehlerstatus).

## `tests/e2e/test_module_status.py`

_Modulzustand zur Laufzeit (GR-102)_

- `check(n, c, i)`
- `nach_id(module)`
- `ob(m, oid)`

## `tests/e2e/test_modulverwaltung.py`

_Modulverwaltung (Roadmap 5, GR-102)_

- `check(n, c, i)`
- `ob(cl, ziel)`
- `kachel(cl, modul)`
- `fehler(b, wort)` – ── Grenzen ──

## `tests/e2e/test_nutzer_anlegen.py`

_Verwaltung → Nutzer anlegen_

- `check(n, c, i)`
- `doc(name)`

## `tests/e2e/test_oidc_dashboard.py`

_Dashboard-Host (dashboard-stafl.de): nur Grundaktionen (lib/herkunft.php, host_nur_grundaktionen, GR-109)._

- `check(n, c, i)`

## `tests/e2e/test_oidc_kern.py`

_Zentrale Anmeldung – Verhalten der Anwendung ohne Keycloak (lib/oidc.php, GR-110)._

- `check(n, c, i)`

## `tests/e2e/test_passkeys.py`

_Passkeys (WebAuthn) für Mitarbeiter-Zugänge._

- `check(n, c, i)`
- `b64u(b)`
- `unb64u(s)`
- `sha(b)`
- `totp(secret, step)`
- `doc(name)`
- `user(name)`
- `log()`
- `logged(a, text, who)`
- `set_user(name, **kw)`
- `session_set(sid, php)`

**CBOR (nur Kodieren) und Software-Authenticator**

- `_head(m, n)`
- `cbor(v)`
- `__init__(alg)`
- `id()`
- `sign(data)`
- `register(opts, origin, rp, flags, typ, challenge, fmt, cose, name)`
- `assertion(opts, origin, rp, flags, typ, challenge, count, handle, bad_sig)`
- `__init__(ip, app)`
- `call(action, data)`
- `login(name, pw)`
- `cookie()`
- `pk_login(key, second, **kw)`
- `pk_register(key, password, **kw)`

**Browser-Hilfen**

- `vauth(pg)`
- `login(pg, name, pw, wait)`
- `logout(pg)`
- `post(pg, action, body)`
- `get(pg, action)`
- `status(pg)`
- `confirm(pg)`
- `open_pk(pg)`
- `no_overflow(pg, sel)`

## `tests/e2e/test_passwortpruefung.py`

_Datenleck-Prüfung der Passwörter („Pwned Passwords“, nachgebauter Dienst auf AUX_PORT): standardmäßig aus; eingeschaltet werden betroffene Passwörter beim Festlegen abgelehnt (Mitarbeiter, Kunden), bestehende bei der …_

- `check(n, c, i)`
- `doc(name)`
- `do_GET()`
- `log_message(*a)`
- `protokoll()`
- `nutzer(name)`

## `tests/e2e/test_protokoll.py`

_Aufbewahrung des Aktivitätsprotokolls (lib/protokoll.php, PROTOKOLL_MONATE = 6; Inhaber 25.10.2026)._

- `check(n, c, i)`
- `monat(zurueck)`

## `tests/e2e/test_rechte.py`

_Nutzerrechte: Rechte je Rolle (einstellbar) und Ausnahmen je Nutzer (erlauben/verbieten)._

- `check(n, c, i)`
- `login(user, pw)`
- `page(user, password, w)`
- `modul(m)`

## `tests/e2e/test_rollen.py`

_Rollen und Rechte: eigene Rollen (anlegen, umbenennen, kopieren, löschen), Modulzugang „<modul>.zugang“ je Rolle, mehrere Rollen je Mitarbeiter, Standardrollen unverändert, Durchsetzung auf dem Server (GR-103), …_

> Testdaten: Vertreter 11 Vera Vertrieb, 12 Tom Tour (Stammdaten → Vertreter); nur synthetische Daten.

- `check(n, c, i)`
- `dokument(name)`
- `anmelden(user, pw)`

**Katalog und Standard**

**Eigene Rolle anlegen**

**Rolle zuordnen**

**Mehrere Rollen**

**CRM: Master-Cockpit, Umsätze in €, Mengen in kg (Auftrag des Inhabers 01.11.2026)**

**Vertreter im CRM am Mitarbeiter (Feld „vertreter“)**

**Standardrolle ändern, Modulzugang entziehen**

**Kopieren, Löschen, Protokoll**

- `seite(user, password, w, ziel)`

## `tests/e2e/test_rollen_host.py`

_Modulzugang je Host: der Testserver meldet sich wie bestand.dashboard-stafl.de (WA_OBERFLAECHE=bestand.intern)._

- `check(n, c, i)`

## `tests/e2e/test_schutz.py`

_Schutzzentrale (Verwaltung → Schutz)_

- `check(n, c, i)`
- `doc(name)`
- `roh(ip, query, ua, data)`
- `bestaetigung_ablaufen(cl)`

**Rechte**

**Falle → automatische Sperre**

**von fremden Seiten ausgelöst: abweisen, aber nicht zählen**

- `fremd(ip, query)`

## `tests/e2e/test_security.py`

_Testgruppe security: Zwei-Faktor-Anmeldung, Wiederherstellungscodes, Sitzungen, IP-Freigabe und Content-Security-Policy._

- `check(n, c, i)`
- `totp(secret, step)`
- `next_step()`
- `login(pg, user, pw, wait)`
- `post(pg, action, body, headers)`
- `add_csp(route)`
- `modul_tab(t)`
- `dialog_ja()`

## `tests/e2e/test_sicherheit_druck.py`

_Sicherheit, Druck und Formatierung_

- `de_datum(iso)` – Datum eines gespeicherten UTC-Zeitstempels in deutscher Zeit (wie Server und Browser es anzeigen).
- `check(n, c, i)`
- `doc(name)`
- `sid_of(cl, name)`
- `session_set(sid, php)`
- `headers(cl, action)`
- `pdf_inhalt(data)`

**Zwei-Faktor: Ersteinrichtung**

**Kein Browser-Cache für angemeldete Antworten**

**Keine internen Importangaben im ausgelieferten Angebot**

**Kunde: Passwort raten begrenzt**

- `kunde(username, firma, angebote, gruppe)`

**Bestell-E-Mail: Betreff mit Jahr, „Warenwert (ca.)“**

**Einzelangebot-PDF: lange Texte**

- `drucken(pg, layout, grouped, scope)`

## `tests/e2e/test_sicherheit_freigaben.py`

_Freigegebene Sicherheitsänderungen_

- `check(n, c, i)`
- `doc(name)`
- `totp(secret, step)`

**Besucher-IP nur vom eigenen Proxy**

**Fehlversuche je IPv6-/64**

**Sperre für unbekannte Namen wie für echte Zugänge**

- `versuche(name, n, start, aktion)`

**gesperrter Zugang mit zweitem Faktor**

- `zweifaktor(name, ip)`
- `nutzer(name)`
- `dauer(name, netz)`

## `tests/e2e/test_sicherheit_it.py`

_Sicherheit für IT-Administratoren_

- `check(n, c, i)`
- `put_raw(name, payload)` – Absichtlich beschädigten Datensatz ablegen (bzw. mit None entfernen) – nur für die Diagnose-Prüfung.

## `tests/e2e/test_sitzung_cookie.py`

_Sitzungs-Cookie mit Präfix __Host- über HTTPS (GR-108, ADR-003 Befund B-1)._

- `check(n, c, i)`
- `roh(action, data, https, cookies, csrf, ip, extra)` – Eine Anfrage; Rückgabe: Status, JSON, Liste der Set-Cookie-Zeilen, Kopfzeilen.
- `cookie(zeilen, name)` – Wert und Attribute (klein geschrieben) des zuletzt gesetzten Cookies „name“, sonst (None, '').
- `wie_https(ctx)` – Origin der API-Anfragen wie hinter Caddy (https://…) – Chromium setzt ihn selbst, daher über route umschreiben.
- `umschreiben(route)`

## `tests/e2e/test_stilllegung.py`

_Alter Eingabebereich stillgelegt (WA_EIGENE_ANMELDUNG=aus, lib/oidc.php): auf dem Host ohne zentrale Anmeldung (angebot-stafl.de) gibt es keine Mitarbeiteranmeldung und keine Mitarbeiteraktionen mehr; die Kundenseite …_

- `check(n, c, i)`

## `tests/e2e/test_storage.py`

_Publication persists consistently; injected storage failures never report success._

- `check(name, condition)`
- `state(db)`

## `tests/e2e/test_testumgebung.py`

_Testumgebung (WA_TESTUMGEBUNG=1)_

- `check(n, c, i)`

## `tests/e2e/test_users.py`

_Testgruppe users: Mitarbeiterzugänge – Rollen, serverseitige Rechte, Protokoll, Sperren und Zwei-Faktor-Pflicht je Nutzer._

- `check(n, c, i)`
- `login(pg, user, pw, wait)`
- `logout(pg)`
- `set_price(pg, code, v)`
- `api_from_page(pg, action, body)`
- `add_user(uname, name, role, pw, must)`
- `fertig()`
- `nutzer_roh(name)`
- `users_modus(route)`

## `tests/e2e/testdaten.py`

_Erwartungswerte aus den anonymisierten Testdaten (tests/fixtures) – statt fest eingetragener Zahlen._

- `de(v)` – 23.3 → '23,30' (deutsches Zahlenformat wie in der Oberfläche).
- `angebot(seed)`
- `artikel(code, seed)`
- `preis(code, seed)`
- `preise(seed)`
- `bestand_kg(code)`
- `excel_preis(code, datei)` – Preis eines Artikels in einer Test-Angebotsliste (Muster: Art.-Nr. \| Bezeichnung \| Preis).

## `tests/e2e/umgebung.py`

_Gemeinsame Pfade für die Ende-zu-Ende-Tests (gesetzt vom Testlauf tests/run_e2e.py)._

- `storage_raw(name)` – Inspect actual persisted state, without going through the application API.
- `storage_sqlite()`
- `storage_write(name, value)` – Gespeichertes Dokument direkt ändern (Testvorbereitung, z. B. Zeitablauf simulieren).
- `storage_docs(prefix)` – Alle gespeicherten Geschäftsdokumente {Name: Inhalt} – unabhängig von der Speicherart.
- `__init__(name)`
- `__enter__()`
- `__exit__(*exc)`
- `wait_text(page, selector, text, timeout)` – Wartet, bis ein Element den Text enthält (statt fester Wartezeit); wirft nicht – die Prüfung danach meldet den Fehler.
- `until(cond, timeout, step)` – Wartet, bis cond() wahr ist (Python-seitig, z. B. Anzahl von Elementen); gibt das letzte Ergebnis zurück.
- `shot(target, path, tries)` – Bildschirmfoto für die Sichtprüfung; ein gerade neu gezeichnetes Element wird erneut versucht (kein Testfehler).

## `tests/oidc/postfach.py`

_Kleiner Test-Mailserver für die Keycloak-Prüfungen (nimmt Nachrichten an, hält sie im Speicher)._

- `__init__(port, user, password)`
- `_annehmen()`
- `_sitzung(c)`
- `an(adresse)`
- `schliessen()`

## `tests/oidc/test_oidc.py`

_Anmeldung über Keycloak (Roadmap 7b, ADR-003, GR-108/GR-110) – Prüfungen gegen die Testumgebung aus umgebung.sh._

- `check(n, c, i)`
- `totp_zaehler(geheim, zaehler)` – Einmalcode wie Keycloak (HmacSHA1, 6 Stellen, 30 s; Schlüssel = Bytes des gespeicherten Geheimnisses).
- `totp(geheim, versatz)` – Noch nie eingegebener, gültiger Einmalcode (aktueller oder nächster Zeitschritt; Keycloak lässt ±1 Schritt zu).
- `redirect_request(*a, **k)`
- `anfrage(url, method, daten, kopf, folgen, jar)`
- `__init__()`
- `call(action, data, _erneut)`
- `protokoll_roh()` – Einträge des Protokolls (Dateispeicher der Testumgebung, aktueller Monat).
- `nutzer_roh()`
- `kc_token()`
- `_ablauf()` – Zustand wie im Betrieb nachstellen: nur die Passwort-Abfrage meldet ihre Anmeldemethode (amr), Einmalcode und Passkey nicht – so hatte „… \| while read“ mit …
- `design_setzen(*args)`
- `realm_jetzt()`
- `anmeldeseite()` – Anmeldeseite von Keycloak wie ein Browser (Weiterleitung vom Dashboard).
- `client_attribute(cid, **attr)` – Attribute eines Clients in Keycloak ändern (Testvorbereitung über die lokale Verwaltungsschnittstelle).
- `bestaetigung_abgelaufen(ctx, host)` – Nachgestellt: die Bestätigung sensibler Aktionen ist abgelaufen (sonst 5 Minuten warten) – PHP-Sitzungsdatei.
- `bestaetigung_stand(ctx, host)` – Zeitpunkt der letzten Bestätigung in der PHP-Sitzung (Diagnose; 0 = abgelaufen).
- `anmelden(pg, wer, otp)`
- `fehlversuch_abstand()` – Keycloak sperrt 60 s, wenn zwei Fehlversuche weniger als 1 s (quickLoginCheckMilliSeconds) auseinanderliegen – der Test wartet daher bis 1,2 s nach dem …
- `otp_eingeben(pg, wer)` – Einmalcode eingeben – immer ein noch nicht verwendeter Code (totp), daher ohne Fehlversuch.
- `eigene_seite(pg)`
- `karte_bereit(seite, sel, timeout)` – Wartet, bis die Detailkarte in `sel` fertig gezeichnet ist (data-karte="bereit": Stil, Kacheln, keine Bewegung).
- `kekse(ctx, host)`
- `do_GET()`
- `do_POST()`
- `log_message(*a)`
- `konten(*args)`
- `env_datei()`
- `vtoken_bf()`
- `vtoken()` – Freiwillig eingerichteter Einmalcode (wie über „Konto“ auf der Anmeldeseite): wird danach immer abgefragt
- `warte_mail(adresse, anzahl)`
- `doc_roh(name)` – Abmelden nach Inaktivität gilt über alle Adressen zusammen (04.11.2026): letzte Aktivität je Anmeldung bei Keycloak im Dokument oidc-aktivitaet.
- `kim_inaktiv(sekunden)`
- `php_sitzung_ruht(host, sekunden)`
- `anmelde_link_vergessen()` – ── Passwort vergessen (Stand 14, konten.sh passwort-vergessen; Inhaber 03.11.2026): Link per Mail an die hinterlegte Adresse, eigener Ablauf ohne „Reset OTP“ …
- `ablauf_datei()`
- `lauf(alias, ebene)`
- `vergessen_anfordern(p_, wer)`
- `link_aus(m_)`
- `geloescht_roh()`

## `tests/regeln/test_regeln.py`

_Tests für werkzeuge/regeln.py: das echte Regelwerk ist stimmig, und typische Verstöße werden erkannt._

- `__init__()`
- `erzeugen()`
- `erzeugen_module()`
- `schreiben(pfad, text)`
- `ersetzen(pfad, alt, neu)`
- `fehler()`
- `entfernen()`
- `setUp()`
- `tearDown()`
- `assertFehler(teiltext)`

## `tests/run_e2e.py`

_Startet für jede Testgruppe einen frischen PHP-Server mit Testdaten und führt die Ende-zu-Ende-Tests aus. python3 tests/run_e2e.py # alle Gruppen (parallel, WA_JOBS Gruppen gleichzeitig) python3 tests/run_e2e.py …_

- `gewicht(name)`
- `teil_lesen(text)` – „k/n“ (1 ≤ k ≤ n) → (k, n); sonst ValueError.
- `teile(namen, n)` – Verteilt die Gruppen auf n Teile mit möglichst gleicher Laufzeit (längste zuerst in den leichtesten Teil).
- `wait_port(port, up, timeout)`
- `admin_file(data)`
- `sqlite_test_seed(data)` – Windows-only fresh test fixture; production migration still runs on Linux/CI.
- `ports(slot)` – Webserver, Hilfsserver, Test-Mailserver 1 und 2 eines Arbeitsplatzes.
- `run(name)`
- `register_anpassen(app, aenderungen)`
- `run_in(name, slot)`
- `adressen_test()` – Adressverzeichnis der Tests aus tests/fixtures/karte/adressen.json (deploy/karte/adressen.py, ohne pyosmium).
- `main()`
- `worker(items)`

## `tests/unit/test_adressen.py`

_Adressverzeichnis der CRM-Karte_

- `check(name, ok, info)`
- `php(eingabe, db)`

## `tests/unit/test_apt_vorrat.py`

_Paketvorrat der CI (.github/scripts/apt_vorrat.py) mit nachgebautem apt-cache. python3 tests/unit/test_apt_vorrat.py Prüft: nur Pakete mit passender SHA-256 aus der (signierten) Paketliste werden übernommen; …_

- `ok(name, cond, info)`

## `tests/unit/test_ci_nachweis.py`

_Nachweis „schon im Pull Request vollständig geprüft“ (.github/scripts/ci_nachweis.py) mit nachgebauter GitHub-API. python3 tests/unit/test_ci_nachweis.py Prüft_

- `ok(name, cond, info)`
- `jobs(tree, **abweichung)`
- `lauf(id_, kopf, **x)`
- `welt(eltern, tree, pulls, laeufe, auftraege)`
- `api_aus(w)`
- `api(pfad)`
- `suche(w, tree, sha)`
- `wackelig(p, _api)`
- `merken(p, _api)`

## `tests/unit/test_doku.py`

_Werkzeug der Entwickler-Dokumentation (werkzeuge/doku.py)_

- `ok(name, cond, info)`

**Abschnitt Detail**

**Laden**

- `methode(a, *rest, **kw)` – Methode mit Docstring.
- `hilfe(x)` – Docstring über mehrere Zeilen.
- `git(*a)`

## `tests/unit/test_run_e2e_teile.py`

_Aufteilung der E2E-Testgruppen auf CI-Aufträge (tests/run_e2e.py_

- `ok(name, cond, info)`

## `werkzeuge/asset_versionen.py`

_Einbindungen der Skripte und Stylesheets in den HTML-Seiten unter app/ und dashboard/ prüfen._

- `seiten()` – (Pfad wie im Browser relativ zur App-Wurzel, Datei): Seiten unter app/ und des Dashboards (/dashboard/ neben app/)
- `main()`

## `werkzeuge/doku.py`

_Nachschlageteil der Entwickler-Dokumentation aus dem Code erzeugen und prüfen (nur Python-Standardbibliothek). python3 werkzeuge/doku.py erzeugen docs/entwickler/referenz/*.md neu schreiben python3 werkzeuge/doku.py …_

- `md(text)` – Text für Markdown-Tabellen: Senkrechtstriche maskieren, Zeilenumbrüche entfernen.

**Kopfkommentare**

- `kopfkommentar(pfad)` – Erste Aussage des Kopfkommentars einer Datei ('' = keiner).
- `_hash_kommentar(zeilen)`
- `_erste_aussage(roh)`
- `braucht_kopf(pfad)`

**API**

- `pruefungen_im_code(wurzel)` – Aktion → (Datei, [Prüfungen]) aus den case-Blöcken der Aktionsdateien.
- `api_md(rw)`

**Rechte**

- `perms_aus_code(wurzel)`
- `rechte_md(rw)`

**Daten, Module, Dateien**

- `daten_md(rw)`
- `module_md(rw)`
- `dateien_md(rw, liste)`

**Funktionen**

- `_kurz(roh)` – Erste Aussage eines Funktionskommentars (bis zum ersten Satzende, Abkürzungen wie „bzw.“ zählen nicht), höchstens FUNK_TEXT_MAX Zeichen.
- `_parameter(sprache, zeilen, i, start)` – Parameternamen ohne Typen und Vorgaben, dazu der Index der Zeile mit der schließenden Klammer.
- `_kommentar_davor(zeilen, i, sprache)` – Kommentar direkt über Zeile i (Block- oder Zeilenkommentar); der Kopfkommentar der Datei zählt nicht.
- `_docstring(zeilen, j)` – Docstring in der Zeile nach der Signatur (Python).
- `funktionen(pfad)` – Abschnitte ('abschnitt', Text) und Funktionen ('funktion', Name, Parameter, Text) einer Datei in Reihenfolge.
- `testdaten_absatz(pfad)` – Absatz „Testdaten:“ aus dem Kopfkommentar einer Testdatei ('' = keiner).
- `funktionen_md(rw, liste)` – Je Modul eine Datei funktionen/<modul>.md und eine Übersicht funktionen/README.md.
- `alle(rw)`
- `main(argv)`

## `werkzeuge/integritaet.py`

_Prüfliste der Dateiprüfung (app/api/lib/integritaet-liste.php): prüfen, dass sie NICHT im Repository steht._

- `git(*args)`
- `main()`

## `werkzeuge/karte_auszug.py`

_Kleiner Ausschnitt aus einer Protomaps-Basiskarte (PMTiles, OpenStreetMap-Daten, ODbL) – für Testdaten und lokale Vorschau der Detailkarte._

- `lade(url, start, laenge)`
- `entpacken(daten, art)`
- `kacheln(lon1, lat1, lon2, lat2, z)`
- `xy(lon, lat)`
- `main()`
- `eintrag(tid)`

## `werkzeuge/lokal.py`

_Lokaler Entwicklungsserver mit Testdaten – wie ein Testserver der E2E-Suite, aber zum Ausprobieren im Browser. python3 werkzeuge/lokal.py http://127.0.0.1:8080 mit Testdaten (tests/fixtures/data-seed) python3 …_

- `main(argv)`

## `werkzeuge/nielsen_gebiete.py`

_Nielsen-Gebiete für die CRM-Karte (app/module/crm/nielsen.json) aus den Bundesländern von Natural Earth erzeugen._

- `runden(geo)`
- `r(c)`
- `main()`

## `werkzeuge/realm_produktion.py`

_Realm „mitarbeiter“ für den Betrieb aus dem geprüften Test-Realm erzeugen (eine Quelle, kein Auseinanderlaufen). python3 werkzeuge/realm_produktion.py # schreibt deploy/anmeldung/realm-mitarbeiter.json python3 …_

- `ersetzen(wert)`
- `erzeugen()`
- `main()`

## `werkzeuge/regeln.py`

_Regelwerk der STAFL-Plattform prüfen und Änderungsfolgen ermitteln (nur Python-Standardbibliothek). python3 werkzeuge/regeln.py pruefen Alle Prüfungen (CI); Ausgang 1 bei Fehlern python3 werkzeuge/regeln.py betroffen …_

**Laden**

- `modulliste()`
- `modul(mid)`
- `modul_ids()`
- `f(text)`
- `w(text)`
- `laden(wurzel)`
- `toml(name)`

**Dateien und Pfadmuster**

- `dateien(wurzel)` – Versionierte Dateien (git ls-files); ohne Git: alle Dateien außer .git und Arbeitsordnern.
- `muster_regex(muster)`
- `passt(muster, pfad)`
- `genauigkeit(muster)` – Exakte Pfade schlagen Muster; sonst gewinnt das längere Muster ohne Platzhalter.
- `eigentuemer(rw, pfad, geplant)` – (modul_id, muster) des genauesten passenden Musters; bei Gleichstand verschiedener Module: Fehlerhinweis.
- `koordination(rw, pfad)`

**Code lesen**

- `dokumentname(name, folgt_verkettung, ist_names)`
- `speicherzugriffe(wurzel, liste)` – Pfad → {'schreibt': set, 'liest': set} für PHP-Dateien unter app/ und deploy/.
- `dokument_eintrag(rw, name)`
- `perms_aus_code(wurzel)`
- `testgruppen_aus_code(wurzel)`
- `ci_schritte(wurzel)`
- `caddy_hosts(wurzel)` – (alle Hosts der dashboard-Domain, Hosts im 503-Platzhalterblock)
- `host(adresse)`

**Zustandsmodell**

- `freigabe_zulaessig(wartung, entwicklung, freigabe)`
- `entscheiden(wartung, lage)` – Erste passende Zeile der Entscheidungstabelle (regeln/wartung.toml, [[regel]]).
- `alle_lagen(wartung)`

**Prüfungen**

- `pruefe_module(rw)`
- `tief(n, weg)`
- `pruefe_pfade(rw, liste)`
- `pruefe_daten(rw, liste)`
- `pruefe_rechte(rw)`
- `test_verweis_ok(rw, t, gruppen, schritte)`
- `pruefe_tests(rw)`
- `pruefe_katalog(rw)`
- `pruefe_wartung(rw)`
- `pruefe_caddy(rw)`

**Aktionsregister**

- `aktionen_im_code(wurzel)` – Aktionen, die der Server tatsächlich bearbeitet: switch-Zweige in app/api/aktionen/*.php, Vergleiche mit $action dort sowie die Listen in orders_action() …
- `aktionen_tabelle(rw)` – Aktion → Eigenschaften mit Standardwerten; doppelte Einträge meldet pruefe_aktionen.
- `php_wert(v)`
- `aktionen_php(rw)`
- `php_ausdruck(v, einzug)` – Python-Wert als PHP-Ausdruck (Listen, Tabellen, Text, Zahl, Wahrheitswert, null) – stabil sortiert nach Eingabe.
- `kachel_ziel(m)`
- `module_php(rw)` – Laufzeitfassung des Modulregisters (ohne Code-Pfade, Agenten oder Hinweise) und der Entscheidungstabelle.
- `pruefe_aktionen(rw)`
- `pruefen(rw)`

**Änderungsfolgen**

- `geaenderte_dateien(wurzel, basis)`
- `git(*args)`
- `nur_doku(pfad)`
- `folgen(rw, liste)`
- `folgen_text(e)`
- `steckbrief(rw, mid)`

**Aufruf**

- `main(argv)`

## `werkzeuge/testdaten_erzeugen.py`

_Erzeugt die anonymisierten Testdaten unter tests/fixtures aus echten Originaldateien._

- `h(*parts)`
- `factor(code, lo, hi)`
- `price(v, code)`
- `anon_offer_xlsx(src, dst)`
- `anon_store(src, dst)`
- `ddmmyyyy(v)`
- `anon_stock(src, dst_xls)` – WinAB-Partieliste: Spalten 1 Art.-Nr., 4 Bezeichnung, 6 EK-Gruppe, 8 VK-Gruppe, 9 Status, 12 Ankunft, 14 Partie, 16 MHD, 18 Kolli, 21 netto kg, 22 EK-Preis.
- `aggregate_stock(path)` – Referenzauswertung (unabhängig von der App): je Artikel Summe kg der eingelagerten Zeilen, frühestes MHD und kg am frühesten MHD.
- `main()`
