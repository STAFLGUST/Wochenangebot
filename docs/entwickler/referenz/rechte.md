# Referenz: Rechte

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: PERMS in app/api/lib/rechte.php, regeln/module.toml, regeln/berechtigungen.toml. Die CI prüft, dass diese Datei zum Code passt. -->

Administratoren haben alle Rechte. Standard = Rechte der Standardrollen ohne gespeicherte Änderung; eigene Rollen starten leer. Erklärung: [04-anmeldung-rechte.md](../04-anmeldung-rechte.md).

## Modulzugang

Für jedes Modul mit Kachel entsteht `<modul>.zugang` (lib/rechte.php, `perms_katalog`): Kachel im Dashboard und Oberfläche des Moduls; Standard: beide Standardrollen.

| Recht | Modul |
| --- | --- |
| `angebot.zugang` | Angebot |
| `bestand.zugang` | Bestand |
| `leergut.zugang` | Leergut |
| `crm.zugang` | CRM |
| `rewe.zugang` | REWE |
| `qs.zugang` | Qualitätssicherung |
| `einkauf.zugang` | Einkauf |
| `containerimport.zugang` | Container-Import |
| `import.zugang` | Import |
| `hr.zugang` | HR |
| `marketing.zugang` | Marketing |
| `controlling.zugang` | Controlling |
| `verwaltung.zugang` | Verwaltung |

## Rechte innerhalb der Module

| Recht | Modul | Bereich | Art | Bezeichnung | Standard | setzt voraus |
| --- | --- | --- | --- | --- | --- | --- |
| `angebot.bearbeiten` | Angebot | Angebot | bearbeiten | Entwurf bearbeiten (Preise, Artikel, Excel-Import, frühere Version laden) | Bearbeiter | – |
| `angebot.veroeffentlichen` | Angebot | Angebot | bearbeiten | Angebot veröffentlichen | Bearbeiter | – |
| `angebote.verwalten` | Angebot | Angebot | bearbeiten | Kundenangebote anlegen und umbenennen | Bearbeiter | – |
| `angebote.loeschen` | Angebot | Angebot | bearbeiten | Kundenangebote löschen, Wochenangebot nur für Kunden sichtbar machen | – | `angebote.verwalten` |
| `preisverlauf.sehen` | Angebot | Preisverlauf | sehen | Preisverlauf ansehen | Nur ansehen, Bearbeiter | – |
| `preisverlauf.bearbeiten` | Angebot | Preisverlauf | bearbeiten | Alte Angebotslisten hochladen und löschen | Bearbeiter | `preisverlauf.sehen` |
| `bestand.sehen` | Bestand | Bestand | sehen | Bestand mit Mengen und MHD ansehen | Nur ansehen, Bearbeiter | – |
| `bestand.einkaufspreise` | Bestand | Bestand | sehen | Einkaufspreise (EK) der Partien im Bestand ansehen | Bearbeiter | `bestand.sehen` |
| `bestand.importieren` | Bestand | Bestand | bearbeiten | Bestandsliste hochladen | Bearbeiter | `bestand.sehen` |
| `stammdaten.sehen` | Verwaltung | Stammdaten | sehen | Stammdaten ansehen | Nur ansehen, Bearbeiter | – |
| `stammdaten.bearbeiten` | Verwaltung | Stammdaten | bearbeiten | Stammdaten bearbeiten | Bearbeiter | `stammdaten.sehen` |
| `einkauf.sehen` | Einkauf | Einkauf | sehen | Einkauf (Fehlmengen) ansehen | Nur ansehen, Bearbeiter | – |
| `einkauf.melden` | Einkauf | Einkauf | bearbeiten | Einkauf per E-Mail benachrichtigen | Bearbeiter | `einkauf.sehen` |
| `hr.antrag` | HR | HR | bearbeiten | Eigenen Urlaub beantragen, Abwesenheitskalender ansehen (nur „abwesend“) | Nur ansehen, Bearbeiter | – |
| `hr.verwalten` | HR | HR | bearbeiten | Personalstelle: Abwesenheiten mit Grund eintragen (nicht für sich selbst), Mitarbeiter, Excel-Export | – | `hr.antrag` |
| `hr.genehmigen` | HR | HR | bearbeiten | Urlaubsanträge genehmigen oder ablehnen (nie den eigenen) | – | `hr.antrag` |
| `crm.sehen` | CRM | CRM | sehen | CRM ansehen: Kunden mit Ansprechpartnern, Wiedervorlagen, Pipeline, Aktivitäten, Auswertung | – | – |
| `crm.bearbeiten` | CRM | CRM | bearbeiten | CRM bearbeiten: Kundenblätter, Ansprechpartner, Interessenten, Aktivitäten erfassen | – | `crm.sehen` |
| `crm.exportieren` | CRM | CRM | bearbeiten | CRM-Liste mit Kontaktdaten als CSV herunterladen | – | `crm.sehen` |
| `marketing.sehen` | Marketing | Marketing | sehen | Redaktionsplan ansehen: Beiträge, Kalender, Board, Kampagnen, CSV | – | – |
| `marketing.bearbeiten` | Marketing | Marketing | bearbeiten | Beiträge und Kampagnen anlegen und ändern, kommentieren, zur Freigabe geben | – | `marketing.sehen` |
| `marketing.freigeben` | Marketing | Marketing | bearbeiten | Beiträge freigeben (veröffentlichungsbereit) und zurückstufen | – | `marketing.bearbeiten` |
| `marketing.verwalten` | Marketing | Marketing | bearbeiten | Einstellungen: Marken, Kanäle, Formate, Content-Säulen; Beiträge löschen | – | `marketing.bearbeiten` |
| `bestellungen.sehen` | Angebot | Bestellungen | sehen | Bestellwünsche mit Kundendaten ansehen | Bearbeiter | – |
| `bestellungen.bearbeiten` | Angebot | Bestellungen | bearbeiten | Bestellwünsche bearbeiten (Status, Notiz, E-Mail erneut senden) | Bearbeiter | `bestellungen.sehen` |
| `kunden.sehen` | Verwaltung | Kunden | sehen | Kundenstammdaten ansehen | – | – |
| `einzelangebote.sehen` | Angebot | Kunden | sehen | Einzelangebote für Kunden ansehen | – | `kunden.sehen` |
| `einzelangebote.bearbeiten` | Angebot | Kunden | bearbeiten | Einzelangebote erstellen, im Portal freigeben und per E-Mail senden | – | `einzelangebote.sehen` |
| `kunden.bearbeiten` | Verwaltung | Kunden | bearbeiten | Kunden anlegen, ändern, löschen, Zugänge und Einladungen | – | `kunden.sehen` |
| `wochenangebot.senden` | Angebot | Kunden | bearbeiten | Wochenangebot per E-Mail an Kunden senden | – | `kunden.sehen` |
| `sonderposten.senden` | Angebot | Kunden | bearbeiten | Sonderposten per E-Mail an Kunden senden | – | `kunden.sehen` |
| `protokoll.sehen` | Verwaltung | Verwaltung | sehen | Protokoll ansehen | – | – |
| `auswertung.sehen` | Verwaltung | Verwaltung | sehen | Auswertung: Karte der Kunden-Anmeldungen ansehen | – | `kunden.sehen` |

## Nur Administratoren

- Nutzer und Rechte verwalten
- Sicherheit und Wartungsmodus
- E-Mail-Postfach, Signatur und Benachrichtigungen
- Module, Freigaben und Wartung je Modul (geplant)
