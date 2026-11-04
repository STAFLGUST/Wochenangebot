<?php
declare(strict_types=1);
/* ERZEUGT von `python3 werkzeuge/regeln.py erzeugen` aus regeln/datenverantwortung.toml (Feld bereich) – nicht von Hand ändern.
   Speicherbereiche (ADR-007 Stufe 2, app/api/storage.php): Dokumente, die die Kundenseite braucht, bleiben im gemeinsamen
   Ordner; alle anderen liegen nach deploy/daten-trennen.sh im Ordner daten-intern, den die Kundenseite nicht sieht. */
if (realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) { http_response_code(404); exit; }

const DATEN_KUNDENSEITE = ['abmelde-schluessel', 'angebot', 'angebote', 'anmeldenamen', 'anmeldeorte', 'bedrohungsliste', 'benachrichtigungen', 'bestand', 'bestellung', 'bestellungen', 'datenleck', 'deployment', 'einzelangebote', 'firewall', 'fracht', 'fw_zaehler', 'kunden', 'kundensitzungen', 'laendersperre', 'logins', 'mail-schluessel', 'mailkonto', 'mailkonto-intern', 'mailvorlage', 'merklisten', 'postausgang', 'postausgang-stand', 'sicherheit', 'sicherheit-notfall', 'sicherung', 'sperrliste', 'stammdaten', 'verkehr', 'wartung'];
const DATEN_KUNDENSEITE_PRAEFIX = ['protokoll/'];
