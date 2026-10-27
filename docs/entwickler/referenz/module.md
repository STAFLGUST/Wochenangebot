# Referenz: Module und Oberflächen

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: regeln/module.toml. Die CI prüft, dass diese Datei zum Code passt. -->

Steckbrief eines Moduls mit Pfaden, Daten, Rechten und Regeln: `python3 werkzeuge/regeln.py modul <id>`. Wer was nutzen darf (Entwicklung/Freigabe/Wartung): `regeln/wartung.toml`.

## Angebot (`angebot`)

Wochenangebot, Kundenangebote, Einzelangebote, Kundenportal, Bestellwünsche, Preisverlauf

Agent: `angebot` · hängt ab von `plattform`, `verwaltung`, `bestand` · Testgruppen: `sys`, `frontend`, `design`, `hist`, `editor_aux`, `revert`, `gemeinsam`, `angebote`, `angebotsliste`, `einzelangebote`, `restposten`, `bestellung`, `order_management`, `order_management_ui`, `order_outbox`, `order_outbox_ui`, `versand`, `kunden_mail`, `web_app`, `legal_pages`, `wartung`, `sidenav`, `p0`, `fehlerpruefung`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `angebot.kunden` Kunden-Frontend | extern | https://angebot-stafl.de/ | fertig | produktiv |
| `angebot.eingabe` Mitarbeiter-Eingabe | intern | https://angebot-stafl.de/admin/ | fertig | produktiv |

## Bestand (`bestand`)

Lagerbestände, Partien/Chargen, MHD, Warenbewegungen, Bestandsauswertungen

Agent: `bestand` · hängt ab von `plattform`, `verwaltung` · Testgruppen: `stock`, `stock_overview`, `bestand_pdf`, `master`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `bestand.intern` Bestand | intern | https://bestand.dashboard-stafl.de/admin/ | fertig | produktiv |

## Leergut (`leergut`)

Leergutkonten je Kunde und Lieferant: Paletten, Kisten und Behälter – Ausgabe, Rücknahme, Salden

Agent: `leergut` · hängt ab von `plattform`, `verwaltung`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `leergut.intern` Leergut | intern | https://leergut.dashboard-stafl.de/ | geplant | keine |

## CRM (`crm`)

Ansprechpartner, Kundenbeziehungen, Aktivitäten, Vorgänge, Vertriebsinformationen

Agent: `crm` · hängt ab von `plattform`, `verwaltung` · Testgruppen: `crm`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `crm.intern` CRM | intern | https://crm.dashboard-stafl.de/module/crm/ | fertig | produktiv |

## REWE (`rewe`)

Eigenständiger Fachbereich REWE – Anforderungen werden separat definiert

Agent: `rewe` · hängt ab von `plattform`, `verwaltung`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `rewe.intern` REWE | intern | https://rewe.dashboard-stafl.de/ | geplant | keine |

## Qualitätssicherung (`qs`)

QS nach IFS Wholesale – jetzt nur technische Grundlage, Fachlogik ist ein eigenes späteres Projekt

Agent: `qs` · hängt ab von `plattform`, `verwaltung`, `bestand`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `qs.intern` QS-Verwaltung | intern | https://qs.dashboard-stafl.de/ | geplant | keine |
| `qs.portal` QS-Portal (Kunden, Lieferanten, Prüfer) | extern | https://qs-stafl.de/ | geplant | keine |

## Einkauf (`einkauf`)

Lieferanten, Einkaufsbestellungen, Bedarfsplanung, Einkaufspreise, Wareneingänge, Liefertermine

Agent: `einkauf` · hängt ab von `plattform`, `verwaltung`, `bestand` · Testgruppen: `einkauf`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `einkauf.intern` Einkauf | intern | https://einkauf.dashboard-stafl.de/ | geplant | keine |

## Container-Import (`containerimport`)

Importcontainer verfolgen: Buchung, Verschiffung, Ankunft, Verzollung und Dokumente

Agent: `containerimport` · hängt ab von `plattform`, `verwaltung`, `einkauf`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `containerimport.intern` Container-Import | intern | https://container-import.dashboard-stafl.de/ | geplant | keine |

## Import (`import`)

Zentrale Importoberfläche für Artikel, Bestände, Preise, Kunden, Lieferanten

Agent: `verwaltung` · Teil von `verwaltung` · hängt ab von `verwaltung`

## HR (`hr`)

Personal: Urlaubsverwaltung – Urlaubsanspruch, Urlaubsanträge, Genehmigung, Vertretung, Abwesenheitskalender

Agent: `hr` · hängt ab von `plattform`, `verwaltung` · Testgruppen: `hr`, `hr_uebersicht`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `hr.intern` HR | intern | https://hr.dashboard-stafl.de/module/hr/ | fertig | produktiv |

## Marketing (`marketing`)

Redaktionsplan für Social Media: Inhalte planen, produzieren, freigeben und veröffentlichen; Kampagnen; später CMS für Website-Inhalte

Agent: `marketing` · hängt ab von `plattform`, `verwaltung` · Testgruppen: `marketing`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `marketing.intern` Marketing | intern | https://marketing.dashboard-stafl.de/module/marketing/ | fertig | produktiv |

## Controlling (`controlling`)

Kennzahlen, Auswertungen und Berichte für Geschäftsführung und Bereiche

Agent: `controlling` · hängt ab von `plattform`, `verwaltung`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `controlling.intern` Controlling | intern | https://controlling.dashboard-stafl.de/ | geplant | keine |

## Verwaltung (`verwaltung`)

Stammdaten, Import, Benutzer, Berechtigungen, Geschäftsregeln, E-Mail, Protokoll

Agent: `verwaltung` · hängt ab von `plattform` · Testgruppen: `kunden`, `kundengruppen`, `vkgruppen`, `vertreter`, `kundenimport`, `auswertung`, `master`, `importzentrale`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `verwaltung.verwaltung` Verwaltung | intern | https://verwaltung.dashboard-stafl.de/admin/ | fertig | produktiv |
| `verwaltung.import` Importzentrale | intern | https://verwaltung.dashboard-stafl.de/import/ | fertig | produktiv |

## Sicherheit (`sicherheit`)

Lagebild, Notfallmodus, Firewall und Sperren, Anmeldung und Sitzungen, Dateiprüfung, Sicherheitsereignisse, Einstellungen, privilegierte Konten und System (Betrieb, Wartung, Module)

Agent: `sicherheit` · hängt ab von `plattform` · Testgruppen: `sicherheit_modul`, `notfall`, `sicherheit_bereitschaft`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `sicherheit.intern` Sicherheit | intern | https://sicherheit.dashboard-stafl.de/module/sicherheit/ | fertig | produktiv |

## Dashboard (`dashboard`)

Zentraler Einstieg: Anmeldung, Kacheln aus dem Modulregister, Modulstatus, Abmeldung

Agent: `dashboard` · hängt ab von `plattform` · Testgruppen: `dashboard`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `dashboard.start` Mitarbeiter-Dashboard | intern | https://dashboard-stafl.de/ | fertig | produktiv |

## App (iOS/Android) (`mobile`)

Expo-App für Kunden und Mitarbeiter; nutzt dieselbe Schnittstelle wie die Website

Agent: `mobile` · hängt ab von `angebot`, `plattform` · Testgruppen: `app_api`, `app_web`

## Plattformkern (`plattform`)

Anmeldung, Sitzungen, Rechte, Sicherheit, Speicherschicht, E-Mail, Protokoll, Betrieb, CI und Regelwerk

Agent: `plattform` · Testgruppen: `einheit`, `rollen`, `rollen_host`, `stilllegung`, `users`, `nutzer_anlegen`, `auth_hardening`, `security`, `passkeys`, `geraete`, `passwortpruefung`, `admin_confirmation`, `admin_confirmation_ui`, `bestaetigung`, `geo`, `geo_ip`, `schutz`, `sicherheit_it`, `sicherheit_freigaben`, `sicherheit_druck`, `integritaet`, `storage`, `benachrichtigung`, `rechte`, `testumgebung`, `app_api`, `sitzung_cookie`, `herkunft`, `modulverwaltung`, `oidc_kern`, `oidc_dashboard`, `anmeldebremse`, `aktionsregister`, `module_status`, `modul_wartung`, `protokoll`

| Oberfläche | Art | Adresse | Entwicklung | Freigabe |
| --- | --- | --- | --- | --- |
| `plattform.anmeldung` Zentrale Mitarbeiteranmeldung (Keycloak, ADR-003) | intern | https://login.dashboard-stafl.de/ | fertig | produktiv |
