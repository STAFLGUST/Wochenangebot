<?php
declare(strict_types=1);
/* Nutzerrechte: was eine Rolle bzw. ein einzelner Nutzer im Eingabebereich sehen und tun darf.
   Administratoren haben immer alle Rechte; Nutzer, Rechte, Sicherheit und E-Mail-Einstellungen bleiben fest
   den Administratoren vorbehalten (sonst könnte sich jemand selbst höhere Rechte geben).
   Gespeichert: Dokument „rechte“ (Rechte je Rolle) und je Nutzer „grant“/„deny“ (Ausnahmen). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Schlüssel => Bereich, Bezeichnung, Art (sehen|machen), Standard-Rollen, setzt voraus; optional „e“ = Standard an auch in
   eigenen Rollen (siehe rights_roles), optional „h“ = Erklärung in Alltagssprache, was das Recht genau erlaubt (und was nicht) –
   erscheint in Verwaltung → Rollen und Rechte unter der Bezeichnung (Auftrag des Inhabers 02.11.2026: „was das genau bedeutet“).
   Die Standards entsprechen dem bisherigen festen Rollenmodell. */
const PERMS = [
    'angebot.bearbeiten'       => ['g' => 'Angebot', 'l' => 'Entwurf bearbeiten (Preise, Artikel, Preisimport, frühere Version laden)', 'k' => 'machen', 'd' => ['editor'], 'r' => []],
    'angebot.veroeffentlichen' => ['g' => 'Angebot', 'l' => 'Angebot veröffentlichen', 'k' => 'machen', 'd' => ['editor'], 'r' => []],
    'angebote.verwalten'       => ['g' => 'Angebot', 'l' => 'Kundenangebote anlegen und umbenennen', 'k' => 'machen', 'd' => ['editor'], 'r' => []],
    'angebote.loeschen'        => ['g' => 'Angebot', 'l' => 'Kundenangebote löschen, Wochenangebot nur für Kunden sichtbar machen', 'k' => 'machen', 'd' => [], 'r' => ['angebote.verwalten']],
    // Export für WinAB (Auftrag des Inhabers 05.11.2026): ohne Standardrollen, nur wer es ausdrücklich bekommt
    'angebot.winab_export'     => ['g' => 'Angebot', 'l' => 'Wochenangebot als CSV für WinAB exportieren (Artikelnummer und Preis des veröffentlichten Angebots)', 'k' => 'machen', 'd' => [], 'r' => []],
    'preisverlauf.sehen'       => ['g' => 'Preisverlauf', 'l' => 'Preisverlauf ansehen', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => []],
    'preisverlauf.bearbeiten'  => ['g' => 'Preisverlauf', 'l' => 'Alte Angebotslisten hochladen und löschen', 'k' => 'machen', 'd' => ['editor'], 'r' => ['preisverlauf.sehen']],
    'bestand.sehen'            => ['g' => 'Bestand', 'l' => 'Bestand mit Mengen und MHD ansehen', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => []],
    'bestand.einkaufspreise'   => ['g' => 'Bestand', 'l' => 'Einkaufspreise (EK) der Partien im Bestand ansehen', 'k' => 'sehen', 'd' => ['editor'], 'r' => ['bestand.sehen']],
    'bestand.mhd_senden'       => ['g' => 'Bestand', 'l' => 'MHD-Liste per E-Mail an den Verkauf senden', 'k' => 'machen', 'd' => ['editor'], 'r' => ['bestand.sehen']],
    'bestand.importieren'      => ['g' => 'Bestand', 'l' => 'Bestandsliste hochladen', 'k' => 'machen', 'd' => ['editor'], 'r' => ['bestand.sehen']],
    'stammdaten.sehen'         => ['g' => 'Stammdaten', 'l' => 'Stammdaten ansehen', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => []],
    'stammdaten.bearbeiten'    => ['g' => 'Stammdaten', 'l' => 'Stammdaten bearbeiten', 'k' => 'machen', 'd' => ['editor'], 'r' => ['stammdaten.sehen']],
    'einkauf.sehen'            => ['g' => 'Einkauf', 'l' => 'Einkauf (Fehlmengen) ansehen', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => []],
    'einkauf.melden'           => ['g' => 'Einkauf', 'l' => 'Einkauf per E-Mail benachrichtigen', 'k' => 'machen', 'd' => ['editor'], 'r' => ['einkauf.sehen']],
    'hr.antrag'                => ['g' => 'HR', 'l' => 'Eigenen Urlaub und Gleittage beantragen', 'k' => 'machen', 'd' => ['viewer', 'editor'], 'r' => [],
                                   'h' => 'Für jeden Mitarbeiter. Sieht nur sich selbst: eigenes Urlaubs- und Gleittage-Konto und eigene Einträge. Kann Urlaub und Gleittage beantragen, zurückziehen und Fehler an die Personalstelle melden. Im Kalender sieht er nur die Kollegen seiner eigenen Abteilung und bei ihnen nur „abwesend“ – nie den Grund (Mitarbeiter sehen im Kalender nur ihre eigene Abteilung; Personalstelle und Urlaubsübersicht sehen alle). Geht erst, wenn die Personalstelle ihn im Urlaubsplan zugeordnet hat.'],
    'hr.verwalten'             => ['g' => 'HR', 'l' => 'Personalstelle: Urlaubsverwaltung pflegen', 'k' => 'machen', 'd' => [], 'r' => ['hr.antrag'],
                                   'h' => 'Für die Personalstelle. Trägt für Kollegen Urlaub, Krank, Gleittage und freie Tage ein (nie für sich selbst) und sieht die Gründe. Pflegt Urlaubsanspruch und Arbeitstage, gewährt Gleittage, erledigt Korrekturmeldungen, stellt Sperren, Ferien und Verfallstag ein, Export für den Steuerberater und Import aus der Zeiterfassung. Genehmigen ist ein eigenes Recht.'],
    'hr.genehmigen'            => ['g' => 'HR', 'l' => 'Anträge genehmigen oder ablehnen', 'k' => 'machen', 'd' => [], 'r' => ['hr.antrag'],
                                   'h' => 'Für Vorgesetzte. Sieht offene Urlaubs- und Gleittag-Anträge mit dem Rest des Mitarbeiters, der Vertretung und wer aus der Abteilung gleichzeitig fehlt – und genehmigt oder lehnt ab. Nie den eigenen Antrag. Krankheiten sieht er nicht.'],
    'hr.uebersicht'            => ['g' => 'HR', 'l' => 'Urlaubsübersicht aller Mitarbeiter ansehen (nur Zahlen)', 'k' => 'sehen', 'd' => [], 'r' => ['hr.antrag'],
                                   'h' => 'Nur ansehen. Je Mitarbeiter und Jahr die Zahlen: Urlaub (Anspruch, genommen, geplant, Rest), Anzahl der Krank- und Gleittage und der Gleittage-Rest. Keine Zeiträume, Gründe oder Notizen. Im Kalender sieht er alle Abteilungen (nur „abwesend“).'],
    // Urlaubskalender (Auftrag des Inhabers 11.11.2026): Kalender mit Urlaub der Kollegen der eigenen Abteilung, aber ohne
    // Tage/Konten/Übersicht. Sensibel (einzeln freigeben, PERMS_SENSIBEL): aus „Urlaub“ und „abwesend“ lassen sich
    // Krankheitstage ableiten.
    'hr.kalender'              => ['g' => 'HR', 'l' => 'Urlaubskalender: Urlaub der Kollegen der eigenen Abteilung sehen (ohne Tage und Konten)', 'k' => 'sehen', 'd' => [], 'r' => ['hr.antrag'],
                                   'h' => 'Für Vorgesetzte oder Schichtleitung. Sieht im Kalender bei den Kollegen der eigenen Abteilung genehmigten Urlaub („U“) und Gleittage („U+“); alle anderen Abwesenheiten nur als „abwesend“ (andere Abteilungen sieht im Kalender nur, wer auch die Urlaubsübersicht hat – dort nur „abwesend“) – nie Krankheit, Gründe, Notizen oder offene Anträge. Wirkt nur, wenn die Person selbst im Urlaubsplan einer Abteilung zugeordnet ist. Keine Tage, kein Urlaubskonto, keine Übersicht. Datenschutz: Wer Urlaub von „abwesend“ unterscheiden kann, kann daraus Krankheitstage ableiten – nur an Personen vergeben, die das sehen dürfen.'],
    'crm.sehen'                => ['g' => 'CRM', 'l' => 'CRM ansehen: Kunden mit Ansprechpartnern, Wiedervorlagen, Pipeline, Aktivitäten, Auswertung', 'k' => 'sehen', 'd' => [], 'r' => []],
    'crm.bearbeiten'           => ['g' => 'CRM', 'l' => 'CRM bearbeiten: Kundenblätter, Ansprechpartner, Interessenten, Aktivitäten erfassen', 'k' => 'machen', 'd' => [], 'r' => ['crm.sehen']],
    'crm.exportieren'          => ['g' => 'CRM', 'l' => 'CRM-Liste mit Kontaktdaten als CSV herunterladen', 'k' => 'machen', 'd' => [], 'r' => ['crm.sehen']],
    'crm.mhd_ware'             => ['g' => 'CRM', 'l' => 'MHD-Ware: Artikel kurz vor Ablauf und ihre Käufer ansehen (Mengen, Liefertage, letzter Kauf aus den Umsatzdaten – keine Preise)', 'k' => 'sehen', 'd' => [], 'r' => ['crm.sehen']],
    // Cockpit je Verkäufer (Auftrag des Inhabers 01.11.2026): Master-Cockpit nur mit eigenem Recht. Umsätze in € und Mengen in kg aus
    // den Umsatzdaten sind einzeln abschaltbar und für die Standardrollen an („Standard an“) – sie wirken nur zusammen mit
    // „CRM ansehen“ und setzen es bewusst nicht voraus (sonst bekäme jeder Mitarbeiter über die Standardrolle das CRM).
    'crm.master'               => ['g' => 'CRM', 'l' => 'CRM: Master-Cockpit – alle Vertreter im Vergleich, Umschalter zur Verkäufer-Ansicht jedes Vertreters (Geschäftsführung)', 'k' => 'sehen', 'd' => [], 'r' => ['crm.sehen']],
    'crm.umsatz_euro'          => ['g' => 'CRM', 'l' => 'CRM: Umsätze in € im Cockpit und im Kunden-Pop-up sehen (aus den Umsatzdaten, ohne Einkaufswerte; wirkt nur mit „CRM ansehen“)', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => [], 'e' => true],
    'crm.umsatz_kg'            => ['g' => 'CRM', 'l' => 'CRM: Mengen in kg im Cockpit und im Kunden-Pop-up sehen (aus den Umsatzdaten; wirkt nur mit „CRM ansehen“)', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => [], 'e' => true],
    'marketing.sehen'          => ['g' => 'Marketing', 'l' => 'Redaktionsplan ansehen: Beiträge, Kalender, Board, Kampagnen, CSV', 'k' => 'sehen', 'd' => [], 'r' => []],
    'marketing.bearbeiten'     => ['g' => 'Marketing', 'l' => 'Beiträge und Kampagnen anlegen und ändern, kommentieren, zur Freigabe geben', 'k' => 'machen', 'd' => [], 'r' => ['marketing.sehen']],
    'marketing.freigeben'      => ['g' => 'Marketing', 'l' => 'Beiträge freigeben (veröffentlichungsbereit) und zurückstufen', 'k' => 'machen', 'd' => [], 'r' => ['marketing.bearbeiten']],
    'marketing.verwalten'      => ['g' => 'Marketing', 'l' => 'Einstellungen: Marken, Kanäle, Formate, Content-Säulen; Beiträge löschen', 'k' => 'machen', 'd' => [], 'r' => ['marketing.bearbeiten']],
    'bestellungen.sehen'       => ['g' => 'Bestellungen', 'l' => 'Bestellwünsche mit Kundendaten ansehen', 'k' => 'sehen', 'd' => ['editor'], 'r' => []],
    'bestellungen.bearbeiten'  => ['g' => 'Bestellungen', 'l' => 'Bestellwünsche bearbeiten (Status, Notiz, E-Mail erneut senden)', 'k' => 'machen', 'd' => ['editor'], 'r' => ['bestellungen.sehen']],
    'kunden.sehen'             => ['g' => 'Kunden', 'l' => 'Kundenstammdaten ansehen', 'k' => 'sehen', 'd' => [], 'r' => []],
    'einzelangebote.sehen'     => ['g' => 'Kunden', 'l' => 'Einzelangebote für Kunden ansehen', 'k' => 'sehen', 'd' => [], 'r' => ['kunden.sehen']],
    'einzelangebote.bearbeiten' => ['g' => 'Kunden', 'l' => 'Einzelangebote erstellen, im Portal freigeben und per E-Mail senden', 'k' => 'machen', 'd' => [], 'r' => ['einzelangebote.sehen']],
    'kunden.bearbeiten'        => ['g' => 'Kunden', 'l' => 'Kunden anlegen, ändern, löschen, Zugänge und Einladungen', 'k' => 'machen', 'd' => [], 'r' => ['kunden.sehen']],
    'wochenangebot.senden'     => ['g' => 'Kunden', 'l' => 'Wochenangebot per E-Mail an Kunden senden', 'k' => 'machen', 'd' => [], 'r' => ['kunden.sehen']],
    'sonderposten.senden'      => ['g' => 'Kunden', 'l' => 'Sonderposten per E-Mail an Kunden senden', 'k' => 'machen', 'd' => [], 'r' => ['kunden.sehen']],
    'protokoll.sehen'          => ['g' => 'Verwaltung', 'l' => 'Protokoll ansehen', 'k' => 'sehen', 'd' => [], 'r' => []],
    // Modul Sicherheit (26.10.2026): ohne Standardrollen; Einstellungen, Sperren, Sitzungen und das Beenden des Notfalls bleiben Administratoren vorbehalten
    'sicherheit.sehen'         => ['g' => 'Sicherheit', 'l' => 'Lagebild, Sicherheitsereignisse und Notfall-Zustand ansehen (nur lesen, mit IP-Adressen und Benutzernamen)', 'k' => 'sehen', 'd' => [], 'r' => ['sicherheit.zugang']],
    'sicherheit.notfall'       => ['g' => 'Sicherheit', 'l' => 'Notfallmodus auslösen (Kunden sehen Wartung, Mitarbeiter ohne Administratorrolle werden ausgesperrt); beenden nur Administratoren', 'k' => 'machen', 'd' => [], 'r' => ['sicherheit.zugang']],
    // Modul Controlling (28.10.2026): je Bereich eigene Rechte, ohne Standardrollen (Finanzdaten); weitere Bereiche (OP-Konten, Liquidität) folgen
    'controlling.umsatz_sehen'      => ['g' => 'Controlling', 'l' => 'Umsatzstatistik ansehen: Monatsmeldung je Vertreter und Auswertung nach Kunde und Artikel (aus den importierten Umsatzdaten)', 'k' => 'sehen', 'd' => [], 'r' => ['controlling.zugang']],
    // Umsatzdaten der Warenwirtschaft (01.11.2026): Auswertung mit umsatz_sehen; Einkaufswerte und Deckungsbeitrag je Kunde/Artikel nur mit eigenem Recht
    'controlling.umsatz_ek'         => ['g' => 'Controlling', 'l' => 'Umsatzauswertung: Einkaufswerte, Deckungsbeitrag und Spanne je Kunde, Artikel und Gruppe sehen (nur zusammen mit „Einkaufspreise (EK) … ansehen“, GR-008)', 'k' => 'sehen', 'd' => [], 'r' => ['controlling.umsatz_sehen']],
    'controlling.umsatz_importieren' => ['g' => 'Controlling', 'l' => 'Umsatzdaten der Warenwirtschaft importieren (Verwaltung → Import, Kundenumsatztabelle)', 'k' => 'machen', 'd' => [], 'r' => ['controlling.umsatz_sehen']],
    // Bereich Bestandsverlauf (02.11.2026): Tagesstände aus den hochgeladenen Bestandslisten (Daten des Moduls Bestand, nur lesend);
    // Lagerwert zum EK nur mit eigenem Recht und zusätzlich bestand.einkaufspreise (GR-008)
    'controlling.bestand_sehen'     => ['g' => 'Controlling', 'l' => 'Bestandsverlauf ansehen: Bestand in kg je Tag, Entwicklung, Reichweite und Umschlag je Artikel und Gruppe (aus den hochgeladenen Bestandslisten)', 'k' => 'sehen', 'd' => [], 'r' => ['controlling.zugang']],
    'controlling.bestand_ek'        => ['g' => 'Controlling', 'l' => 'Bestandsverlauf: Lagerwert zum Einkaufspreis sehen (nur zusammen mit „Einkaufspreise (EK) … ansehen“, GR-008)', 'k' => 'sehen', 'd' => [], 'r' => ['controlling.bestand_sehen']],
    // Bereich Arbeitszeit (02.11.2026): Zeitbericht der Zeiterfassung (Personaldaten mit Namen) – Soll, Ist, Saldo je Mitarbeiter
    // und Abteilung, Stempelfehler; ohne Standardrollen, sensibel (einzeln freigeben)
    'controlling.arbeitszeit_sehen' => ['g' => 'Controlling', 'l' => 'Arbeitszeit ansehen: Soll, Ist und Saldo je Mitarbeiter und Abteilung, Stempelfehler (aus dem importierten Zeitbericht der Zeiterfassung, Personaldaten mit Namen)', 'k' => 'sehen', 'd' => [], 'r' => ['controlling.zugang']],
    'controlling.arbeitszeit_importieren' => ['g' => 'Controlling', 'l' => 'Zeitbericht der Zeiterfassung importieren (Verwaltung → Import)', 'k' => 'machen', 'd' => [], 'r' => ['controlling.arbeitszeit_sehen']],
    // Modul Leergut (29.10.2026): ohne Standardrollen – Administratoren vergeben die Rechte (Salden und Werte gegenüber Partnern)
    'leergut.sehen'            => ['g' => 'Leergut', 'l' => 'Leergutkonten ansehen: Salden, Bewegungen, Abstimmungen mit Fristen, Dachser-Abschreibungen, Bilanz, CSV', 'k' => 'sehen', 'd' => [], 'r' => []],
    'leergut.bearbeiten'       => ['g' => 'Leergut', 'l' => 'Leergut buchen: Bewegungen buchen und stornieren, Auszüge erfassen und bestätigen/widersprechen, Abschreibungen und Inventur pflegen', 'k' => 'machen', 'd' => [], 'r' => ['leergut.sehen']],
    'leergut.verwalten'        => ['g' => 'Leergut', 'l' => 'Leergut verwalten: Partner und Lademittel mit Werten pflegen, Datenpaket übernehmen', 'k' => 'machen', 'd' => [], 'r' => ['leergut.bearbeiten']],
    // Modul REWE (30.10.2026): ohne Standardrollen – Administratoren vergeben die Rechte (Kundenkontakte und Mengen der Märkte)
    'rewe.sehen'               => ['g' => 'REWE', 'l' => 'REWE: eigene Liste und Akten der eigenen Märkte ansehen (Wochenverlauf, Notizen)', 'k' => 'sehen', 'd' => [], 'r' => []],
    'rewe.bearbeiten'          => ['g' => 'REWE', 'l' => 'REWE: eigene Märkte abfragen (Bestellungen der Woche), Notizen, Wiedervorlagen, Kaufbereitschaft, Dauerauftrag, Ansprechpartner', 'k' => 'machen', 'd' => [], 'r' => ['rewe.sehen']],
    'rewe.alle'                => ['g' => 'REWE', 'l' => 'Alle REWE-Listen sehen (mit „bearbeiten“ auch für andere abfragen, z. B. Vertretung)', 'k' => 'sehen', 'd' => [], 'r' => ['rewe.sehen']],
    'rewe.verwalten'           => ['g' => 'REWE', 'l' => 'REWE verwalten: Märkte anlegen, Zuweisung und Lieferweg ab KW, Lieferwege und Artikel, Excel-Listen übernehmen', 'k' => 'machen', 'd' => [], 'r' => ['rewe.bearbeiten', 'rewe.alle']],
    'rewe.exportieren'         => ['g' => 'REWE', 'l' => 'REWE-Wochenabschluss: Bestellungen aller Listen, Excel für WinAB, „in WinAB erfasst“', 'k' => 'machen', 'd' => [], 'r' => ['rewe.alle']],
    // Modul Qualitätssicherung · QM-System (30.10.2026): ohne Standardrollen – Administratoren bündeln die Rechte in eigenen Rollen (z. B. QMB, QM-Kontrollen Lager)
    'qs.sehen'                 => ['g' => 'Qualitätssicherung', 'l' => 'QM-System ansehen: Dokumente mit Versionen, QM-Handbuch, Prüfplan mit Nachweisen, Maßnahmen, CSV', 'k' => 'sehen', 'd' => [], 'r' => []],
    'qs.nachweis'              => ['g' => 'Qualitätssicherung', 'l' => 'Kontrollen durchführen: Nachweise für die eigenen (zugewiesenen) Prüfungen erfassen', 'k' => 'machen', 'd' => [], 'r' => ['qs.sehen']],
    'qs.bearbeiten'            => ['g' => 'Qualitätssicherung', 'l' => 'QM-System bearbeiten: Dokumente anlegen und überarbeiten (Entwurf, zur Prüfung geben), Nachweise aller Prüfungen erfassen und stornieren, Maßnahmen erfassen', 'k' => 'machen', 'd' => [], 'r' => ['qs.nachweis']],
    'qs.freigeben'             => ['g' => 'Qualitätssicherung', 'l' => 'QM-System prüfen und freigeben (QMB, Geschäftsführung): Dokumente prüfen, freigeben, einziehen, als überprüft vermerken (nie eigene Entwürfe prüfen), Handbuch und Prüfplan ändern, Maßnahmen als wirksam abschließen', 'k' => 'machen', 'd' => [], 'r' => ['qs.bearbeiten']],
    'qs.verwalten'             => ['g' => 'Qualitätssicherung', 'l' => 'QM-System verwalten: Kapitel, Personen (Kürzel und Verknüpfung mit Mitarbeitern) und Einstellungen pflegen, Datenpaket übernehmen', 'k' => 'machen', 'd' => [], 'r' => ['qs.bearbeiten']],
    'auswertung.sehen'         => ['g' => 'Verwaltung', 'l' => 'Auswertung: Karte der Kunden-Anmeldungen ansehen', 'k' => 'sehen', 'd' => [], 'r' => ['kunden.sehen']],
];
/* Darstellung in Verwaltung → Rollen und Rechte (nur Anzeige, keine Prüfung – durchgesetzt wird weiter je Aktion mit
   require_perm, GR-103). Die Oberfläche fasst die Rechte eines Moduls zu Stufen zusammen: Ansehen (Art „sehen“),
   Bearbeiten (Art „machen“), Voll (zusätzlich freigeben, verwalten, löschen: PERMS_STUFE_VOLL). Sensible Rechte
   (PERMS_SENSIBEL: Einkaufswerte, Kontaktdaten-Export, Personaldaten, Kundenzugänge, Notfall) gehören zu keiner Stufe und
   werden einzeln freigegeben. PERMS_VORSCHAU: Vorschau-Bild je Recht (admin-rollen-vorschau.js, nur Beispieldaten);
   der Modulzugang zeigt immer die Kachel. Gespeichert wird weiter nur die Liste der Rechte – Stufen sind nicht gespeichert
   (GR-006, keine Migration). Neue Rechte ohne Eintrag erscheinen nach ihrer Art (Auftrag des Inhabers 02.11.2026). */
const PERMS_STUFE_VOLL = ['angebot.veroeffentlichen', 'angebote.loeschen', 'wochenangebot.senden', 'sonderposten.senden', 'leergut.verwalten',
    'crm.master', 'rewe.alle', 'rewe.verwalten', 'rewe.exportieren', 'qs.freigeben', 'qs.verwalten', 'hr.genehmigen', 'hr.uebersicht',
    'marketing.freigeben', 'marketing.verwalten'];
const PERMS_SENSIBEL = ['bestand.einkaufspreise', 'crm.exportieren', 'controlling.umsatz_ek', 'controlling.bestand_ek', 'controlling.arbeitszeit_sehen',
    'controlling.arbeitszeit_importieren', 'hr.verwalten', 'hr.kalender',
    'kunden.bearbeiten', 'sicherheit.notfall'];
const PERMS_VORSCHAU = ['bestand.sehen' => 'bestand', 'bestand.einkaufspreise' => 'ek', 'bestand.importieren' => 'import', 'bestand.mhd_senden' => 'mhd',
    'angebot.veroeffentlichen' => 'veroeffentlichen', 'crm.umsatz_euro' => 'umsatz', 'crm.exportieren' => 'export', 'controlling.umsatz_ek' => 'spanne',
    'controlling.bestand_ek' => 'lagerwert', 'hr.genehmigen' => 'genehmigen', 'kunden.bearbeiten' => 'kundenzugang', 'sicherheit.notfall' => 'notfall'];
/* Fest den Administratoren vorbehalten (nur zur Anzeige in der Rechte-Übersicht) */
const PERMS_ADMIN_ONLY = ['Mitarbeiter (Anmeldung) und Rechte verwalten', 'Sicherheit und Wartungsmodus', 'E-Mail-Postfach, Signatur und Benachrichtigungen'];
/* Standardrollen (Rechte im Dokument „rechte“, wie bisher). Eigene Rollen stehen im Dokument „rollen“ (siehe unten). */
const PERM_ROLES = ['viewer', 'editor'];

/* ---------- Rechtekatalog: PERMS + Modulzugang je Kachel ----------
   Modulzugang „<modul>.zugang“ (Roadmap 7b, GR-103): darf die Kachel im Dashboard sehen und die Oberfläche des Moduls
   öffnen. Er entsteht aus dem Modulregister (jedes Modul mit Kachel) – neue Module bekommen ihn ohne Code-Änderung.
   Standard: beide Standardrollen (so bleibt der bisherige Zugang aller Mitarbeiter unverändert), außer das Register nennt
   andere (Feld zugang_rollen, z. B. Sicherheit: keine). Die Rechte innerhalb
   eines Moduls (PERMS) hängen nicht davon ab: ein Recht kann auch in einem anderen Modul genutzt werden (z. B. Kunden
   sehen im Angebot), der Modulzugang sperrt nur die Oberfläche des Moduls (modul_zugang_durchsetzen). */
function perms_katalog(): array
{
    static $k = null;
    if ($k !== null) return $k;
    $k = [];
    foreach (MODULE as $id => $m) {
        if (empty($m['dashboard']) || empty($m['kachel_ziel'])) continue;
        // Standardrollen mit Zugang: Registerfeld zugang_rollen (z. B. [] = nur Administratoren und ausdrücklich Berechtigte), sonst beide
        $std = is_array($m['zugang_rollen'] ?? null) ? array_values(array_intersect($m['zugang_rollen'], PERM_ROLES)) : PERM_ROLES;
        $k["$id.zugang"] = ['g' => $m['name'], 'l' => 'Modul „' . $m['name'] . '“ öffnen (Kachel im Dashboard)', 'k' => 'zugang', 'd' => $std, 'r' => [], 'm' => $id];
    }
    foreach (PERMS as $key => $p) $k[$key] = $p + ['m' => recht_modul($key)];
    return $k;
}
/* Modul eines Rechts: Zuordnung aus regeln/berechtigungen.toml (erzeugt: RECHTE_MODUL), sonst Präfix „<modul>.“ */
function recht_modul(string $key): string
{
    if (isset(RECHTE_MODUL[$key])) return RECHTE_MODUL[$key];
    $m = explode('.', $key, 2)[0];
    return isset(MODULE[$m]) ? $m : 'plattform';
}

/* ---------- Rollen ----------
   admin: fest, alle Rechte · viewer/editor: Standardrollen (Rechte im Dokument „rechte“, Name änderbar) ·
   eigene Rollen „r<8 hex>“ im Dokument „rollen“: {eigene: {id: {name, beschreibung, rechte, erstellt, von, geaendert, geaendertVon}},
   namen: {viewer|editor: Name}}. Ein Mitarbeiter hat eine Rolle („role“, wie bisher) und optional weitere („rollen“, nur
   eigene oder Standardrollen) – die Rechte addieren sich. Format nur erweitert (GR-006): ältere Fassungen lesen „role“. */
function rollen_dok(bool $neu = false): array
{
    static $d = null;
    if ($neu || $d === null) { $x = store_read('rollen'); $d = is_array($x) ? $x : []; }
    return $d;
}
function rollen_eigene(): array
{
    $out = [];
    foreach ((array)(rollen_dok()['eigene'] ?? []) as $id => $r) {
        if (is_string($id) && preg_match('/^r[0-9a-f]{8}$/', $id) && is_array($r) && is_string($r['name'] ?? null)) $out[$id] = $r;
    }
    return $out;
}
function rolle_existiert(string $id): bool { return $id === 'admin' || in_array($id, PERM_ROLES, true) || isset(rollen_eigene()[$id]); }
function rolle_name(string $id): string
{
    if (in_array($id, PERM_ROLES, true)) { $n = rollen_dok()['namen'][$id] ?? ''; return is_string($n) && $n !== '' ? $n : ROLE_LABELS[$id]; }
    if ($id === 'admin') return ROLE_LABELS['admin'];
    return (string)(rollen_eigene()[$id]['name'] ?? $id);
}
/* Alle Rollen eines Mitarbeiters (bekannte, ohne Doppelte); Administrator nur als Hauptrolle */
function user_rollen(array $u): array
{
    $r = (string)($u['role'] ?? '');
    if ($r === 'admin') return ['admin'];
    $alle = array_merge([$r], array_map('strval', (array)($u['rollen'] ?? [])));
    return array_values(array_unique(array_filter($alle, fn($x) => $x !== 'admin' && rolle_existiert($x))));
}
function rollen_text(array $u): string { return implode(', ', array_map('rolle_name', user_rollen($u))) ?: '–'; }

/* Rechte je Rolle (Standardrollen gespeichert oder Standard, dazu die eigenen Rollen).
   „bekannt“ (Dokument „rechte“) = Katalog beim letzten Speichern: Rechte, die danach neu hinzukamen, bekommen die
   Standardrollen mit ihrem Standardwert – sonst verlöre z. B. jeder Mitarbeiter mit dem neuen Modulzugang alle Kacheln.
   Ältere Dokumente ohne „bekannt“ kannten genau PERMS (der Modulzugang ist dort neu) – außer den Rechten mit „e“, die erst
   danach dazukamen. Rechte mit „e“ (Standard an auch in eigenen Rollen, z. B. CRM: Umsätze in € und Mengen in kg) gelten
   zusätzlich in jeder eigenen Rolle, bis ein Administrator die Rolle gespeichert hat („bekannt“ der Rolle, rolle_save) –
   danach zählt nur noch seine Auswahl. */
function rights_roles(): array
{
    $d = store_read('rechte') ?? [];
    $kat = perms_katalog();
    $fuerAlle = array_keys(array_filter(PERMS, fn($p) => !empty($p['e'])));
    $bekannt = is_array($d['bekannt'] ?? null) ? $d['bekannt'] : array_values(array_diff(array_keys(PERMS), $fuerAlle));
    $out = [];
    foreach (PERM_ROLES as $r) {
        $std = array_keys(array_filter($kat, fn($p) => in_array($r, $p['d'], true)));
        if (is_array($d['roles'][$r] ?? null)) {
            $neu = array_values(array_filter($std, fn($k) => !in_array($k, $bekannt, true)));
            $out[$r] = rights_close(array_values(array_unique(array_merge(rights_clean($d['roles'][$r]), $neu))));
        } else $out[$r] = $std;
    }
    foreach (rollen_eigene() as $id => $rl) {
        $kennt = is_array($rl['bekannt'] ?? null) ? $rl['bekannt'] : [];
        $dazu = array_values(array_filter($fuerAlle, fn($k) => !in_array($k, $kennt, true)));
        $out[$id] = rights_close(rights_clean(array_merge((array)($rl['rechte'] ?? []), $dazu)));
    }
    return $out;
}
function rights_clean(array $list): array { return array_values(array_unique(array_intersect(array_keys(perms_katalog()), array_map('strval', $list)))); }
/* Voraussetzungen ergänzen (wer bearbeiten darf, darf auch sehen) */
function rights_close(array $perms): array
{
    $kat = perms_katalog();
    $set = array_flip($perms);
    do {
        $added = false;
        foreach (array_keys($set) as $p) foreach ($kat[$p]['r'] ?? [] as $req) if (!isset($set[$req])) { $set[$req] = true; $added = true; }
    } while ($added);
    return array_values(array_intersect(array_keys($kat), array_keys($set)));
}
/* Wirksame Rechte eines Nutzers: alle Rollen + erlaubt − verboten (Administrator: alle) */
function user_perms(array $u, ?array $roles = null): array
{
    $kat = perms_katalog();
    if (($u['role'] ?? '') === 'admin') return array_keys($kat);
    $roles = $roles ?? rights_roles();
    $p = [];
    foreach (user_rollen($u) as $r) $p = array_merge($p, $roles[$r] ?? []);
    $p = array_merge($p, rights_clean((array)($u['grant'] ?? [])));
    $p = rights_close(array_values(array_unique($p)));
    $deny = rights_clean((array)($u['deny'] ?? []));
    // Verbotenes entfernen, dann alles, dessen Voraussetzung jetzt fehlt
    $p = array_values(array_diff($p, $deny));
    do {
        $n = count($p);
        $p = array_values(array_filter($p, function ($k) use ($p, $kat) { foreach ($kat[$k]['r'] as $req) if (!in_array($req, $p, true)) return false; return true; }));
    } while (count($p) !== $n);
    return $p;
}
function may(array $u, string $perm): bool { return in_array($perm, user_perms($u), true); }
function require_perm(string $perm, bool $write = false): array
{
    $u = require_auth($write);
    if (!may($u, $perm)) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
    return $u;
}
/* Wie require_admin_confirmation, aber für ein Recht statt der Administratorrolle.
   $key: Aktion im Katalog BESTAETIGUNG – ist die Bestätigung dort abgeschaltet, genügen Anmeldung und Recht. */
function require_perm_confirmed(string $perm, string $key = ''): array
{
    if ($key !== '' && !bestaetigung_noetig($key)) return require_perm($perm, true);
    $u = require_perm($perm, true);
    confirmation_locked($u);
    $at = (int)($_SESSION['adminConfirmedAt'] ?? 0);
    if ($at <= time() && $at > time() - bestaetigung_sekunden() && (int)($_SESSION['adminConfirmedSv'] ?? -1) === (int)$u['sv']) return $u;
    // Keycloak-Host: kein eigenes Passwort – Bestätigung durch erneute Anmeldung bei Keycloak, wie bei Administratoren
    // (require_admin_confirmation). Ohne diese Zeile bekäme die Oberfläche „confirmation_required“, öffnete die
    // Passwortabfrage und liefe in die dort gesperrte Aktion reauth (403) – die Aktion wäre nicht mehr bestätigbar.
    if (oidc_modus()) oidc_neu_anmelden();
    respond(['ok' => false, 'code' => 'confirmation_required', 'error' => 'Bitte bestätigen Sie diese Aktion mit Ihrem aktuellen Passwort.'], 403);
}

/* ---------- Modulzugang durchsetzen (GR-103: serverseitig, nicht über die Kachel) ----------
   Kachel: nur mit eigenem „<modul>.zugang“. Oberfläche (Host): mit dem Zugang des Moduls oder eines Teilmoduls
   („teil_von“, z. B. Import → Verwaltung: die Importzentrale liegt auf dem Verwaltungs-Host). Module ohne Kachel
   (Dashboard, Plattformkern) brauchen keinen Zugang. */
function modul_zugang_frei(?array $u, string $modul, ?array $perms = null): bool
{
    if (!isset(perms_katalog()["$modul.zugang"])) return true;
    if (!$u) return false;
    return in_array("$modul.zugang", $perms ?? user_perms($u), true);
}
/* Angemeldet UND Modulzugang „<modul>.zugang“ – unabhängig vom Host der Anfrage (GR-103). Für lesende Aktionen, die
   Inhalte eines Moduls ausliefern und sonst nur die Anmeldung prüfen würden (z. B. Entwurf und Kundenpreise des Angebots,
   die der gemeinsame Eingabebereich auch auf anderen Hosts abrufen kann). Bewusst ohne code „kein_modulzugang“: der
   ersetzt in der Oberfläche die ganze Seite (Host ohne Zugang) – hier geht es nur um einzelne Inhalte eines Bereichs. */
function require_modulzugang(string $modul, bool $write = false): array
{
    $u = require_auth($write);
    if (modul_zugang_frei($u, $modul)) return $u;
    header('Cache-Control: no-store');
    fail('Dafür fehlt Ihnen der Zugang zum Bereich „' . (MODULE[$modul]['name'] ?? $modul) . '“. Bitte an einen Administrator wenden.', 403);
}
function modul_host_frei(?array $u, string $modul): bool
{
    $teile = [$modul];
    foreach (MODULE as $id => $m) if (($m['teil_von'] ?? null) === $modul) $teile[] = $id;
    $mit = array_values(array_filter($teile, fn($m) => isset(perms_katalog()["$m.zugang"])));
    if (!$mit) return true;
    if (!$u) return false;
    $p = user_perms($u);
    foreach ($mit as $m) if (in_array("$m.zugang", $p, true)) return true;
    return false;
}
/* Modul der Oberfläche dieser Anfrage: der Host (Webserver: WA_OBERFLAECHE, nie aus Kopfzeilen) – sonst die Oberfläche der
   Aktion, außer dem gemeinsamen Eingabebereich ohne eigenen Host (angebot.eingabe: dort liegen heute Angebot, Bestand,
   Verwaltung zusammen; die Sichtbarkeit regeln dort die Einzelrechte) */
function anfrage_modul(?array $aktion): ?string
{
    $host = oidc_einstellung('WA_OBERFLAECHE');
    if ($host !== '') return explode('.', $host, 2)[0];
    $ob = (string)($aktion['oberflaeche'] ?? '');
    if ($ob === '' || $ob === 'angebot.eingabe') return null;
    return explode('.', $ob, 2)[0];
}
function modul_zugang_durchsetzen(?array $aktion): void
{
    if ($aktion === null || $aktion['oeffentlich'] || $aktion['wartung_frei']) return;
    if (in_array($aktion['modul'], ['plattform', 'dashboard'], true)) return;   // eigener Zugang, Status, Rollenprüfung im Kern
    $m = anfrage_modul($aktion);
    if ($m === null) return;
    $u = current_user();
    if (!$u || modul_host_frei($u, $m)) return;   // ohne Anmeldung: die Aktion meldet selbst „Bitte erneut anmelden“
    header('Cache-Control: no-store');
    $name = MODULE[$m]['name'] ?? $m;
    respond(['ok' => false, 'code' => 'kein_modulzugang', 'modul' => $m, 'name' => $name,
             'error' => 'Sie haben keinen Zugang zum Bereich „' . $name . '“. Bitte an einen Administrator wenden.'], 403);
}

function rights_catalog(): array
{
    $out = [];
    foreach (perms_katalog() as $k => $p) {
        // Stufe und Vorschau nur für die Darstellung (siehe PERMS_STUFE_VOLL); Felder nur ergänzt, ältere Oberflächen ignorieren sie
        $stufe = $p['k'] === 'zugang' ? 'zugang' : (in_array($k, PERMS_SENSIBEL, true) ? 'sensibel'
            : (in_array($k, PERMS_STUFE_VOLL, true) ? 'voll' : ($p['k'] === 'sehen' ? 'ansehen' : 'bearbeiten')));
        $out[] = ['key' => $k, 'group' => $p['g'], 'label' => $p['l'], 'kind' => $p['k'], 'requires' => $p['r'], 'default' => $p['d'], 'modul' => $p['m'], 'eigene' => !empty($p['e']), 'hilfe' => (string)($p['h'] ?? ''),
                  'stufe' => $stufe, 'sensibel' => $stufe === 'sensibel', 'vorschau' => $p['k'] === 'zugang' ? 'kachel' : (string)(PERMS_VORSCHAU[$k] ?? '')];
    }
    return $out;
}
/* Rollenübersicht für die Verwaltung (Administrator): Rechte, Name, Anzahl Mitarbeiter */
function rollen_liste(?array $roles = null, ?array $users = null): array
{
    $roles = $roles ?? rights_roles();
    $users = $users ?? users_load();
    $zahl = fn($id) => count(array_filter($users, fn($u) => nutzer_hat_zugang($u) && in_array($id, user_rollen($u), true)));
    $out = [['id' => 'admin', 'name' => rolle_name('admin'), 'beschreibung' => 'Alle Rechte, dazu Mitarbeiter und Rechte, Sicherheit und E-Mail-Einstellungen',
             'art' => 'fest', 'rechte' => array_keys(perms_katalog()), 'mitarbeiter' => $zahl('admin')]];
    $besch = ['viewer' => 'Standardrolle: nur ansehen', 'editor' => 'Standardrolle: Angebot bearbeiten und veröffentlichen, Bestellungen, Bestand'];
    foreach (PERM_ROLES as $r) $out[] = ['id' => $r, 'name' => rolle_name($r), 'beschreibung' => $besch[$r], 'art' => 'standard', 'rechte' => $roles[$r], 'mitarbeiter' => $zahl($r)];
    $eigene = rollen_eigene();
    uasort($eigene, fn($a, $b) => strcasecmp((string)$a['name'], (string)$b['name']));
    foreach ($eigene as $id => $rl) $out[] = ['id' => $id, 'name' => (string)$rl['name'], 'beschreibung' => (string)($rl['beschreibung'] ?? ''), 'art' => 'eigen',
        'rechte' => $roles[$id] ?? [], 'mitarbeiter' => $zahl($id), 'geaendert' => $rl['geaendert'] ?? null, 'geaendertVon' => (string)($rl['geaendertVon'] ?? '')];
    return $out;
}
/* Module für die Rechte-Übersicht: Kachel-Module in Dashboard-Reihenfolge, dazu „plattform“ für Rechte ohne Modul */
function rechte_module(): array
{
    $out = [];
    foreach (MODULE as $id => $m) {
        $kachel = !empty($m['dashboard']) && !empty($m['kachel_ziel']);
        $hat = array_filter(perms_katalog(), fn($p) => $p['m'] === $id);
        if (!$kachel && !$hat) continue;
        $frei = false;
        if ($kachel) { [$zm, $zo] = explode('.', (string)$m['kachel_ziel'], 2); $frei = modul_freigabe($zm, $zo) === 'produktiv'; }
        $out[] = ['id' => $id, 'name' => $m['name'], 'beschreibung' => $m['beschreibung'], 'icon' => $m['icon'], 'teil_von' => $m['teil_von'], 'kachel' => $kachel, 'freigegeben' => $frei];
    }
    return $out;
}
