<?php
declare(strict_types=1);
/* STAFL-Plattform · Modul Container-Import – Tracking: wo ist der Container, wann kommt er an (Auftrag des Inhabers
   19.11.2026: eigener Reiter neben EUDR; Schiffsname eintragen; wissen, wann der Container z. B. in Hamburg oder Rotterdam
   ankommt). Erste Stufe ohne fremde Dienste: Schiff, Reederei, Konnossement, Abgangs- und Zielhafen, geplante Abfahrt und
   Ankunft stehen am Container und werden von Hand gepflegt – auch nach dem Abschluss der EUDR-Bewertung, der Container reist
   weiter. Zur Sendungsverfolgung der Reederei führt ein Verweis (CI_REEDEREIEN); abgefragt wird dort nichts.
   Die Felder liegen im Dokument der Container (containerimport-eudr-sendungen, nur erweitert, GR-006); älteren Einträgen
   ergänzt eudr_sendungen() sie beim Lesen. Speicher- und Prüfhelfer stehen in eudr.php.
   Bedeutung, an der spätere Stufen festhalten: die Felder beschreiben die Reise im Ganzen und den Plan, wie er von Hand
   gepflegt wird – schiff = das Schiff, das im Zielhafen ankommt; etd/eta = geplante Abfahrt und Ankunft. Abgerufene
   Meldungen (Hafenliste, HVCC, Tracking-Dienst) kommen nie in diese Felder, sondern in ein eigenes Dokument mit Abrufzeit
   und werden beim Lesen dazugestellt; Etappen einer Umladung kämen als eigene Liste dazu. */
if (!defined('WA_API')) { http_response_code(404); exit; }

/* Felder des Trackings am Container mit ihrem Wert für Einträge, die sie noch nicht haben */
const CI_TRACKING_VORGABEN = ['schiff' => '', 'reederei' => '', 'bl' => '', 'abgangshafen' => '', 'zielhafen' => '', 'etd' => '', 'eta' => ''];

/* Reedereien zur Auswahl: Name, Seite ihrer Sendungsverfolgung („{nr}“ = Containernummer ohne Leerzeichen; ohne Platzhalter
   öffnet sich die Suchmaske) und Kürzel eigener Container, aus denen die Seite einen Vorschlag ableitet. Gemietete
   Container tragen fremde Kürzel – der Vorschlag ist nur eine Hilfe, gespeichert wird die Wahl.
   Die Adressen ändern sich gelegentlich: hier anpassen (der Browser setzt nur die Containernummer ein, tracking.js).
   Die Schlüssel (maersk, sonst …) stehen an den Containern: nie umbenennen oder entfernen, nur ergänzen (GR-006). */
const CI_REEDEREIEN = [
    'maersk' => ['name' => 'Maersk (auch Hamburg Süd, Sealand)', 'url' => 'https://www.maersk.com/tracking/{nr}', 'kuerzel' => ['MSKU', 'MAEU', 'MRKU', 'MRSU', 'SUDU', 'SEAU']],
    'msc' => ['name' => 'MSC', 'url' => 'https://www.msc.com/en/track-a-shipment', 'kuerzel' => ['MSCU', 'MEDU', 'MSDU', 'MSMU']],
    'hapag' => ['name' => 'Hapag-Lloyd', 'url' => 'https://www.hapag-lloyd.com/en/online-business/track/track-by-container-solution.html?container={nr}', 'kuerzel' => ['HLCU', 'HLXU', 'HLBU']],
    'cmacgm' => ['name' => 'CMA CGM', 'url' => 'https://www.cma-cgm.com/ebusiness/tracking', 'kuerzel' => ['CMAU', 'CGMU', 'ECMU', 'APLU']],
    'one' => ['name' => 'ONE (Ocean Network Express)', 'url' => 'https://ecomm.one-line.com/one-ecom/manage-shipment/cargo-tracking', 'kuerzel' => ['ONEU', 'NYKU']],
    'cosco' => ['name' => 'COSCO', 'url' => 'https://elines.coscoshipping.com/ebusiness/cargotracking', 'kuerzel' => ['CSNU', 'CCLU', 'CBHU']],
    'evergreen' => ['name' => 'Evergreen', 'url' => 'https://ct.shipmentlink.com/servlet/TDB1_CargoTracking.do', 'kuerzel' => ['EGHU', 'EISU', 'EMCU']],
    'zim' => ['name' => 'ZIM', 'url' => 'https://www.zim.com/tools/track-a-shipment', 'kuerzel' => ['ZIMU', 'ZCSU']],
    'hmm' => ['name' => 'HMM', 'url' => 'https://www.hmm21.com/', 'kuerzel' => ['HMMU', 'HDMU']],
    'sonst' => ['name' => 'Andere Reederei', 'url' => '', 'kuerzel' => []],
];

/* Angaben des Trackings aus der Eingabe prüfen (genau die Felder aus CI_TRACKING_VORGABEN). Fehlt eine Angabe, bleibt der
   gespeicherte Wert. Stand und Containernummer, die das Fenster „Tracking“ mitpflegt, prüft ci_reise in eudr.php. */
function ci_tracking_pruefen(array $b, array $alt): array
{
    $b += array_intersect_key($alt, CI_TRACKING_VORGABEN);
    foreach (['etd' => 'Abfahrt', 'eta' => 'Ankunft'] as $k => $was) {   // eudr_datum liest alles, was kein Text ist, als leer – hier wäre das ein gelöschtes Datum
        if ($b[$k] !== null && !is_string($b[$k])) throw new InvalidArgumentException("$was: bitte ein gültiges Datum angeben.");
    }
    $etd = eudr_datum($b['etd'], 'Abfahrt');
    $eta = eudr_datum($b['eta'], 'Ankunft');
    if ($etd !== '' && $eta !== '' && $eta < $etd) throw new InvalidArgumentException('Die Ankunft liegt vor der Abfahrt.');
    return [
        'schiff' => eudr_text($b['schiff'], 80, 'Schiff'),
        'reederei' => eudr_wahl($b['reederei'], array_keys(CI_REEDEREIEN), 'Reederei', ''),
        'bl' => eudr_text($b['bl'], 40, 'Konnossement'),
        'abgangshafen' => eudr_text($b['abgangshafen'], 80, 'Abgangshafen'),
        'zielhafen' => eudr_text($b['zielhafen'], 80, 'Zielhafen'),
        'etd' => $etd, 'eta' => $eta,
    ];
}
