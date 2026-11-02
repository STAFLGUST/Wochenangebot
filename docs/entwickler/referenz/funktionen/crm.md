# Funktionen: CRM (`crm`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

7 Dateien, 151 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/crm.php`

_Aktionen: CRM · Vertrieb (Oberfläche crm.intern, Daten und Regeln in app/api/module/crm/crm.php) Rechte (GR-103): crm.sehen – Kunden, Kundenblätter, Wiedervorlagen, Pipeline, Auswertung, Karte ansehen (crm_karte); …_

- `crm_key_param(v)` – Schlüssel aus der Anfrage (Kunden-ID der Verwaltung oder Interessent „i…“)
- `crm_eintrag(key)` – Ein Eintrag der Liste (nach dem Speichern an die Oberfläche zurück)

## `app/api/module/crm/cockpit.php`

_CRM · Mein Cockpit, Master-Cockpit und die Übersicht im Kunden-Pop-up (Auftrag des Inhabers 01.11.2026)._

- `crm_kundenbild()` – Schnittstelle des Controllings laden (nur, wenn das CRM Zahlen braucht)
- `crm_zahlrechte(me)` – Welche Zahlen darf der Mitarbeiter sehen?
- `crm_um(w, r)` – [Umsatz, Menge] → nur die erlaubten Werte: umsatz (Cent), menge (Tausendstel kg)
- `crm_zahlen_filtern(x, r)` – Felder umsatz…/menge… (auch in Listen darin) ohne das jeweilige Recht entfernen
- `crm_cockpit_ansicht(me, wunsch)` – Ansicht: 'vertreter' (Nummer), 'master' (alle), 'ohne_vertreter' (Master: Kunden ohne Vertreter) oder 'ohne' (kein Vertreter zugeordnet, kein Master-Recht: …
- `crm_im_bereich(c, a)` – Gehört der Kunde der Verwaltung zur Ansicht?
- `crm_signal_gewicht(s, r)` – Reihenfolge der Signale je Art: wirtschaftlich größte zuerst – nach dem, was der Mitarbeiter sehen darf (€, sonst kg)
- `crm_cockpit(me, wunsch)` – Cockpit der Ansicht: Kennzahlen (Monat und Jahr bis zum Stand mit Vorjahr, 365 Tage), Signale, Top-Kunden und – im Master-Cockpit – die Vertreter im …
- `crm_cockpit_vergleich(stamm, kb, r)` – Master-Cockpit: je Vertreter (und „ohne Vertreter“) aktive Kunden, Umsatz/Menge im Monat mit Vorjahr und in 365 Tagen, Signale
- `crm_kunde_umsatz(me, key)` – Übersicht im Kunden-Pop-up: Umsatz und Menge (365 Tage mit Vorjahr), Monate mit Vorjahr, letzter Kauf, Rhythmus, Preisniveau (nur mit € und kg), Top-Artikel, …

## `app/api/module/crm/crm.php`

_CRM · Vertrieb: Daten und Regeln des Moduls „crm“ (Oberfläche crm.intern, Aktionen in app/api/aktionen/crm.php) Kundenstammdaten (Nummer, Firma, Anschrift, Telefon, E-Mail, Vertreter, Gruppe, aktiv) gehören der …_

- `crm_rhythmen()` – Anruf-Rhythmen (Wiedervorlage „Wann“) wie in der bisherigen Vertriebsliste

**Laden und Schreiben**

- `crm_kunden_doc()`
- `crm_interessenten_doc()`
- `crm_aktivitaeten_doc()`
- `crm_schreiben(name, doc)`
- `crm_id(praefix)`

**Stammdaten der Verwaltung (nur lesend, Schnittstelle des Eigentümers)**

- `crm_vertreter()`
- `crm_stammkunden()` – Kunden der Verwaltung: Kunden-ID → Kunde
- `crm_schluessel_gueltig(key)` – Ist der Schlüssel ein Kunde der Verwaltung oder ein Interessent des CRM?
- `crm_firma_nr(key)`
- `crm_ist_aktiv(key)` – Aktiv-Stand eines Kunden bzw. Interessenten – derselbe Standard für „Aktiv in der Wiedervorlage“ wie in crm_liste

**Prüfen der Eingaben**

- `crm_datum(v, was)`
- `crm_zahl(v, was)`
- `crm_wahl(v, erlaubt, was, leer)`
- `crm_text(v, max, was)`
- `crm_email(v, was)`
- `crm_kontakte(v)`
- `crm_felder()` – Felder eines Kundenblatts: Name => [Bezeichnung, Prüfung, im Protokoll mit Wert]
- `crm_standard(interessent, aktiv)` – Standardwerte eines Kundenblatts (nichts gespeichert = Standard)
- `crm_blatt(e, interessent, aktiv)` – Gespeichertes Kundenblatt auf bekannte Felder beschränken (ältere/neuere Fassungen bleiben lesbar, GR-006)

**Interessenten**

- `crm_interessent_pruefen(b, alt)`

**Liste für die Oberfläche**

- `crm_liste()` – Kunden der Verwaltung und Interessenten mit Kundenblatt; Angebote nur als Namen (Schnittstelle des Angebots)
- `crm_karte_punkte()` – Karte: Koordinaten der Anschriften aus dem Adressverzeichnis des Servers (lib/adressen.php) – je Kunde bzw. Interessent [Breite, Länge, 'h' \| 's'] …
- `crm_aktivitaet_aus(a)` – Aktivität für die Oberfläche (ohne interne Kennungen der Person)
- `crm_protokoll_aenderungen(key, nr, alt, neu)` – Protokolleintrag (GR-106 unberührt): ohne Kontaktdaten und Notizen – nur Kundennummer, Feld und bei Auswahlfeldern der Wert
- `crm_csv(liste, vertreter)` – CSV (Semikolon, UTF-8 mit BOM – öffnet in Excel direkt richtig)

**MHD-Ware: Artikel kurz vor Ablauf und ihre Käufer (Recht crm.mhd_ware, Auftrag des Inhabers 01.11.2026)**

- `crm_mhd_monate(v)`
- `crm_mhd_zeitraum(monate, heute)` – Zeitraum „letzte n Monate“ bis heute (einschließlich): Beginn am Tag nach dem gleichen Tag n Monate früher – am Monatsende ohne Überlauf (31.05. → ab 01.03., …
- `crm_mhd_liste()`
- `crm_artikel_code(v)`
- `crm_key_je_nr()` – Kundennummer (ohne führende Nullen) → Schlüssel des Kundenblatts
- `crm_mhd_artikel(code, liste)` – Artikel mit MHD-Angaben (aus der MHD-Liste) bzw. Name aus den Umsatzdaten
- `crm_schluessel_menge()` – Alle gültigen Schlüssel (Kunden der Verwaltung und Interessenten) mit [Firma, Kundennummer, aktiv] – einmal gelesen statt je Schlüssel …
- `crm_mhd_schritt(a)` – Text des nächsten Schritts für die Wiedervorlage („MHD-Ware anbieten: Rinderhüfte (40100), MHD 06.11.“)

## `app/module/crm/cockpit.js`

_STAFL-Plattform · CRM · Cockpit (Auftrag des Inhabers 01.11.2026)_

**Zahlen (Umsatz in Cent, Menge in Tausendstel kg)**

**Bereich der Ansicht (für Wiedervorlagen, Chancen, Aktivitäten aus crm_start)**

- `imBereich(k, d)`
- `heuteDran(liste, d)` – Heute dran: fällige Wiedervorlagen (überfällige zuerst), Bestellpausen (Signal des Servers), Anrufe laut Rhythmus

**Laden**

- `laden(wahl)`
- `zeichne(host, c)`

**Bausteine**

- `kachel(titel, wert, sub, x, cls)`
- `pauseText(s)`
- `wenigerText(s)`
- `wegText(s)`
- `heuteZeile(h)`
- `signalZeile(s)`
- `balken(reihe)` – Zwölf Monatsbalken (Umsatz, sonst Menge); der laufende Monat (bis zum Stand) heller
- `chancen(liste, titel)`
- `aktivitaeten(liste, titel)`

**Kopf mit Umschalter (Master)**

- `kopf(d, n)`

**Cockpit zeichnen**

- `rendern()`
- `wertEuro(s)` – Wirtschaftliches Gewicht eines Signals in Cent (Master: Sortierung „Auffällige Kunden“)
- `topKunden(d)`
- `vergleich(d)`

**Bedienung**

- `signale()` – Erstes Signal eines Kunden aus dem geladenen Cockpit (Kundenliste: Kennzeichen und Auswahl „Mit Signal“)

**Kunden-Pop-up: Reiter „Übersicht“**

- `uebersicht(host, key, c)`
- `uebersichtZeichnen(host, key, u)`
- `artikelTabelle(x, r)`
- `auffaellig(x)`
- `naechsterSchritt(k)`
- `plusTage(iso, n)`
- `ansprechpartner(k)`

## `app/module/crm/crm.js`

_STAFL-Plattform · CRM · Vertrieb Cockpit, Kunden, Wiedervorlagen (Anruf-Rhythmus), Pipeline, Karte und Auswertung – nach der Vertriebs-CRM-Musterdatei._

- `api(action, body, query)`
- `toast(text, fehler)`

**Datum, Zahlen, Namen**

- `namen(k)` – Alle Ansprechpartner (Stammdaten + Kundenblatt) und Telefonnummern eines Kunden
- `telefone(k)`
- `kw(d)` – Anruf-Rhythmus: in wie vielen Tagen ist der nächste Termin?
- `naechsterAnruf(r)`

**Kopf, Anmeldung, Thema**

- `fehler(text)`
- `zeigeAnmeldung(ziel)`
- `themaKnopf()`

**Reiter**

- `zeigeTab(tab)`
- `zeichne()`
- `mhd()` – Reiter „MHD-Ware“ (mhd-ware.js, Recht crm.mhd_ware): Hilfsfunktionen des CRM für das Skript des Reiters

**Daten**

- `setzeDaten(d)`
- `ersetze(k)` – Eintrag nach dem Speichern ersetzen (Server liefert den ganzen Eintrag zurück)
- `speichereFelder(key, felder)`

**Cockpit (cockpit.js): Mein Cockpit, Master-Cockpit**

- `kpi(titel, w, zusatz, cls)`
- `cockpit()`

**Kunden**

- `kundenListe()`
- `suchText(k)` – Durchsuchbarer Text eines Kunden (Kundenliste und Kartensuche), zwischengespeichert bis zum nächsten Laden
- `kunden()`

**Wiedervorlagen (Anrufliste)**

- `wvReihenfolge()`
- `wvListe()`
- `wiedervorlagen(nurTabelle)`

**Pipeline**

- `pipeline()`

**Karte (eigene Zeichnung, Web-Mercator wie die Auswertung der Verwaltung)**

- `ladeGeo()`
- `ladeAdressen()` – Genaue Lage der Anschriften (crm_karte: Adressverzeichnis auf dem Server, OpenStreetMap) – höchstens einmal pro Minute neu; fehlt das Verzeichnis oder …
- `kartenPlz(k)` – PLZ eines Kunden für die Karte: nur Deutschland (5-stellig; 4-stellig ohne Land = führende 0 fehlt)

**Nielsen-Gebiete (Bundesländer zusammengefasst, nielsen.json)**

- `imRing(lon, lat, ring)`
- `inFlaeche(lon, lat, g)`
- `gebietVon(lon, lat)` – Nielsen-Gebiet eines Punkts; knapp außerhalb der vereinfachten Grenzen (Küste, Grenzorte) das nächstgelegene
- `kundenLage(k, lagen)` – Lage eines Kunden: genaue Anschrift (Hausnummer bzw. Straße), sonst Mittelpunkt der PLZ, sonst null
- `kartenPunkte(lagen)` – Punkte der Karte: gleiche Lage = ein Punkt. id: „a<Breite>,<Länge>“ bzw. die PLZ; genau: 'haus' \| 'strasse' \| 'plz'. proGebiet zählt alle Kunden der Auswahl …
- `gebietsFlaechen(proGebiet)`
- `gebietsPfade(sammlung)` – Gebiete als SVG-Pfade der eigenen Zeichnung (gleiche Projektion wie die Punkte)
- `seitenVerhaeltnis(b)`
- `karte()`
- `detailkarteZeigen(punkte, kamera, flaechen)` – Detailkarte (Straßen, Gebäude) statt eigener Zeichnung, wenn die Kartendatei auf dem Server liegt und der Browser WebGL kann – sonst bleibt die Übersichtskarte.
- `kartenGenauigkeit(zahl, stand)` – Hinweis unter der Karte: wie genau die Punkte liegen
- `kartenPopZu()`
- `kartenAusschnitt()`
- `gebietZeigen(id)` – Ausschnitt eines Nielsen-Gebiets (Detailkarte bzw. eigene Zeichnung)
- `gebieteAktualisieren()` – Schalter „Gebiete zeigen“: Flächen neu, ohne die Karte neu aufzubauen

**Kundensuche auf der Karte**

- `suchTreffer(zeigen)`
- `zeigeKunde(key)` – Gefundenen Kunden zeigen: Filter so stellen, dass er sichtbar ist, hinzoomen, Infokarte öffnen
- `kartenZoom(f, cx, cy)`
- `kartenPos(ev)`
- `kartenPop(plz, kundeKey)`

**Auswertung**

- `auswertung()`

**Kundenblatt**

- `feld(label, name, k, typ, extra)`
- `auswahl(label, name, k, liste, leer)`
- `kontaktZeile(p)`
- `stammdaten(k)`
- `kuReiter(k)`
- `kuTabZeigen(tab)`
- `oeffne(key, tab)`
- `ladeVerlauf(key)`
- `kuAktivitaeten(key)` – Übersicht: die letzten drei Aktivitäten (aus dem geladenen Verlauf)
- `blattStatus(text, art)`
- `kontakteAusFormular()`

**Interessent**

- `interessentDialog(k)`
- `speichereInteressent()`

**Klicks**

- `exportieren()`

**Start**

- `laden()`

## `app/module/crm/mhd-ware.js`

_STAFL-Plattform · CRM · Reiter „MHD-Ware“ (Auftrag des Inhabers 01.11.2026): links die Artikel kurz vor Ablauf aus der MHD-Liste des Bestands – in denselben Farben wie dort (abgelaufen, 0–4, 5–7, 8–14 Tage) –, rechts …_

- `mhdText(a, heute)`
- `listeLaden()`
- `kaeuferLaden()`

**Links: MHD-Liste und Suche**

- `zeichneListe()`

**Rechts: Käufer des gewählten Artikels**

- `kaeuferZeilen()`
- `zeichneKaeufer()`
- `zeichneAlles()`

**Bedienung**

- `verbinden()`
- `zeichne(host, c)` – Aufruf aus crm.js: host = Reiterfläche, c = Hilfsfunktionen des CRM

## `tests/e2e/test_crm.py`

_CRM · Vertrieb (Modul crm, Oberfläche crm.intern unter /module/crm/)._

> Testdaten: Vertreter 11 Vera Vertrieb, 12 Tom Tour; Kundengruppe 5 Fleischereien Nord. Kunden 900001 Musterfleischerei Nord (Hamburg, Kundenzugang, Angebot std), 900002 Beispiel Catering (Kiel, Vertreter 12 und 11), 900003 Probe Markt Ost (Dresden, PLZ ohne führende 0), 900004 Alpen Feinkost (Österreich, kein Kartenpunkt), 900005 Ruhender Handel (inaktiv), 900006 Test-Gastro Süd (ohne Vertreter). Nutzer: verena (sehen), bert (bearbeiten), xena (bearbeiten und exportieren), otto (ohne Recht), nora (sehen); für die MHD-Ware mia (sehen und MHD-Ware) und max (bearbeiten und MHD-Ware). MHD-Ware: Bestand relativ zu heute (700001 abgelaufen, 700002 in 3 Tagen, 700003 in 10 Tagen, 700004 in 30 Tagen = nicht in der Liste) und Umsatzzeilen ROH relativ zu heute (Käufe vor 10/40/70/120/200 Tagen für 3/6/12 Monate, Gutschrift, ohne Berechnung, Kunde 999999 ohne Stammsatz). Cockpit: Umsatzzeilen über zwei Jahre bis zum Stand (heute − 2), wöchentlich: 900001 kauft 40100 seit 70 Tagen nicht mehr, 900002 seit 35 Tagen nichts (Bestellpause), 900003 kauft −50 % zum Vorjahr, 900006 neu (vor 20 Tagen), 999999 ohne Stammsatz, Leergut; EK-Werte als Erkennungszahl (777777/888888). Nutzer vv (Vertreter 11), gf (Master), vk (nur kg), vn (ohne € und kg).

- `check(n, c, i)`
- `dokument(name)`
- `kunde(i, nr, firma, plz, ort, land, aktiv, vt, vt2, angebote, **extra)`
- `anmelden(user, pw, ip, breite, thema)`
- `vj(d_)`
- `summe(kunden, von, bis)`
- `seite(user, pw, ip, breite, thema)`
