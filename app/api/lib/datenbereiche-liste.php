<?php
declare(strict_types=1);
/* ERZEUGT von `python3 werkzeuge/regeln.py erzeugen` aus regeln/datenverantwortung.toml (Feld bereich) – nicht von Hand ändern.
   Speicherbereiche (ADR-007 Stufe 2, app/api/storage.php): Dokumente, die die Kundenseite braucht, bleiben im gemeinsamen
   Ordner; alle anderen liegen nach deploy/daten-trennen.sh im Ordner daten-intern, den die Kundenseite nicht sieht.
   DATEN_AB_STUFE: interne Dokumente, die erst mit dieser Trennstufe umziehen (bis dahin im gemeinsamen Ordner).
   KUNDEN_FELDER_KUNDENSEITE: ab Trennstufe 2 bleiben nur diese Felder eines Kunden im Dokument kunden (Rest: kundenstamm).
   DATEN_VEROEFFENTLICHT: ab ihrer Trennstufe schreibt und liest die Mitarbeiterseite sie innen und legt eine Kopie in den
   gemeinsamen Ordner; die Kundenseite liest nur die Kopie und kann sie nicht schreiben. */
if (realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) { http_response_code(404); exit; }

const DATEN_KUNDENSEITE = ['abmelde-schluessel', 'anmeldenamen', 'anmeldeorte', 'bestellungen', 'datenleck', 'deployment', 'fw_zaehler', 'kunden', 'kundensitzungen', 'laendersperre', 'logins', 'mail-schluessel', 'merklisten', 'postausgang', 'sicherung', 'sperrliste', 'verkehr'];
const DATEN_KUNDENSEITE_PRAEFIX = ['kundenprotokoll/'];
const DATEN_TRENNSTUFE = 4;
const DATEN_AB_STUFE = ['angebot' => 3, 'angebote' => 3, 'artikelauszug' => 3, 'bedrohungsliste' => 3, 'benachrichtigungen' => 2, 'bestand' => 2, 'bestellung' => 3, 'einzelangebote' => 3, 'firewall' => 3, 'fracht' => 3, 'mailkonto' => 2, 'mailkonto-intern' => 2, 'mailvorlage' => 2, 'postausgang-stand' => 3, 'sicherheit' => 3, 'sicherheit-notfall' => 3, 'stammdaten' => 2, 'wartung' => 3];
const DATEN_AB_STUFE_PRAEFIX = ['protokoll/' => 4];
const KUNDEN_FELDER_KUNDENSEITE = ['id', 'nr', 'firma', 'ansprechpartner', 'gruppe', 'angebote', 'active', 'login', 'mailAngebot', 'abgemeldet', 'emailMaske'];
const DATEN_VEROEFFENTLICHT = ['angebot', 'angebote', 'artikelauszug', 'bedrohungsliste', 'bestellung', 'einzelangebote', 'firewall', 'fracht', 'postausgang-stand', 'sicherheit', 'sicherheit-notfall', 'wartung'];
