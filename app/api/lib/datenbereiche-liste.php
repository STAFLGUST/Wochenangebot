<?php
declare(strict_types=1);
/* ERZEUGT von `python3 werkzeuge/regeln.py erzeugen` aus regeln/datenverantwortung.toml (Feld bereich) – nicht von Hand ändern.
   Speicherbereiche (ADR-007 Stufe 2, app/api/storage.php): Dokumente, die die Kundenseite braucht, bleiben im gemeinsamen
   Ordner; alle anderen liegen nach deploy/daten-trennen.sh im Ordner daten-intern, den die Kundenseite nicht sieht.
   DATEN_AB_STUFE: interne Dokumente, die erst mit dieser Trennstufe umziehen (bis dahin im gemeinsamen Ordner).
   KUNDEN_FELDER_KUNDENSEITE: ab Trennstufe 2 bleiben nur diese Felder eines Kunden im Dokument kunden (Rest: kundenstamm). */
if (realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) { http_response_code(404); exit; }

const DATEN_KUNDENSEITE = ['abmelde-schluessel', 'angebot', 'angebote', 'anmeldenamen', 'anmeldeorte', 'artikelauszug', 'bedrohungsliste', 'bestellung', 'bestellungen', 'datenleck', 'deployment', 'einzelangebote', 'firewall', 'fracht', 'fw_zaehler', 'kunden', 'kundensitzungen', 'laendersperre', 'logins', 'mail-schluessel', 'merklisten', 'postausgang', 'postausgang-stand', 'sicherheit', 'sicherheit-notfall', 'sicherung', 'sperrliste', 'verkehr', 'wartung'];
const DATEN_KUNDENSEITE_PRAEFIX = ['protokoll/'];
const DATEN_TRENNSTUFE = 2;
const DATEN_AB_STUFE = ['benachrichtigungen' => 2, 'bestand' => 2, 'mailkonto' => 2, 'mailkonto-intern' => 2, 'mailvorlage' => 2, 'stammdaten' => 2];
const KUNDEN_FELDER_KUNDENSEITE = ['id', 'nr', 'firma', 'ansprechpartner', 'gruppe', 'angebote', 'active', 'login', 'mailAngebot', 'abgemeldet', 'emailMaske'];
