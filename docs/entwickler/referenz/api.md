# Referenz: API-Aktionen

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: regeln/aktionen/*.toml, Rechteprüfungen in app/api/aktionen/*.php. Die CI prüft, dass diese Datei zum Code passt. -->

Aufruf: `/api/?action=<aktion>` (GET lesend, POST mit JSON und `X-CSRF-Token` schreibend). Ablauf im Server: [03-server.md](../03-server.md), Rechte: [04-anmeldung-rechte.md](../04-anmeldung-rechte.md). „Prüfung im Code“ ist aus den Aufrufen `require_perm`/`require_auth`/`require_admin_confirmation`/`current_customer` im `case`-Block gelesen – eine Hilfe zum Finden, maßgeblich ist der Code (Prüfungen in aufgerufenen Funktionen erscheinen hier nicht).

Spalten: **Art** – lesend, schreibend (nur POST) oder post (GET liest, POST schreibt); **Kennzeichen** – öffentlich (ohne Mitarbeiteranmeldung), Kunden-Wartung, wartungsfrei, fremde Herkunft, eigene Anmeldung (siehe [regeln/aktionen/LIESMICH.md](../../../regeln/aktionen/LIESMICH.md)).

218 Aktionen in 13 Modulen.

## Angebot (`angebot`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `abmelden1` | `angebot.kunden` | lesend | öffentlich, fremde Herkunft | – | `app/api/aktionen/kundenportal.php` |
| `angebot_artikel` | `angebot.eingabe` | lesend | – | Recht angebot.bearbeiten | `app/api/aktionen/angebote.php` |
| `bestell_settings_save` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/kundenportal.php` |
| `bestellung` | `angebot.eingabe` | lesend | – | siehe Datei | `app/api/aktionen/kundenportal.php` |
| `bestellung_mail_retry` | `angebot.eingabe` | schreibend | – | siehe Datei | `app/api/orders.php` |
| `bestellung_save` | `angebot.eingabe` | schreibend | – | siehe Datei | `app/api/orders.php` |
| `bestellungen` | `angebot.eingabe` | lesend | – | siehe Datei | `app/api/aktionen/kundenportal.php` |
| `discard_draft` | `angebot.eingabe` | schreibend | – | Recht angebot.bearbeiten | `app/api/aktionen/entwurf.php` |
| `draft` | `angebot.eingabe` | lesend | – | – | `app/api/aktionen/entwurf.php` |
| `draft_ping` | `angebot.eingabe` | schreibend | – | angemeldet | `app/api/aktionen/entwurf.php` |
| `einzel_artikel` | `angebot.eingabe` | lesend | – | Recht einzelangebote.bearbeiten | `app/api/aktionen/einzelangebote.php` |
| `einzel_detail` | `angebot.eingabe` | lesend | – | Recht einzelangebote.sehen | `app/api/aktionen/einzelangebote.php` |
| `einzel_liste` | `angebot.eingabe` | lesend | – | Recht einzelangebote.sehen | `app/api/aktionen/einzelangebote.php` |
| `einzel_loeschen` | `angebot.eingabe` | schreibend | – | Recht einzelangebote.bearbeiten | `app/api/aktionen/einzelangebote.php` |
| `einzel_pdf` | `angebot.eingabe` | lesend | – | Recht einzelangebote.sehen | `app/api/aktionen/einzelangebote.php` |
| `einzel_save` | `angebot.eingabe` | schreibend | – | Recht einzelangebote.bearbeiten | `app/api/aktionen/einzelangebote.php` |
| `einzel_senden` | `angebot.eingabe` | schreibend | – | Recht einzelangebote.bearbeiten + Bestätigung | `app/api/aktionen/einzelangebote.php` |
| `einzel_status` | `angebot.eingabe` | schreibend | – | Recht einzelangebote.bearbeiten | `app/api/aktionen/einzelangebote.php` |
| `fracht_save` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/kundenportal.php` |
| `history_data` | `angebot.eingabe` | lesend | – | Recht preisverlauf.sehen | `app/api/aktionen/preisverlauf.php` |
| `history_delete` | `angebot.eingabe` | schreibend | – | Recht preisverlauf.bearbeiten | `app/api/aktionen/preisverlauf.php` |
| `history_import` | `angebot.eingabe` | schreibend | – | Recht preisverlauf.bearbeiten | `app/api/aktionen/preisverlauf.php` |
| `history_list` | `angebot.eingabe` | lesend | – | Recht preisverlauf.sehen | `app/api/aktionen/preisverlauf.php` |
| `history_prev` | `angebot.eingabe` | lesend | – | angemeldet | `app/api/aktionen/preisverlauf.php` |
| `kunde_abmelden` | `angebot.kunden` | schreibend | öffentlich | – | `app/api/aktionen/kundenportal.php` |
| `kunde_abmelden_info` | `angebot.kunden` | schreibend | öffentlich | – | `app/api/aktionen/kundenportal.php` |
| `kunde_bestellung` | `angebot.kunden` | schreibend | öffentlich, Kunden-Wartung | Kunde | `app/api/aktionen/kundenportal.php` |
| `kunde_bestellung_detail` | `angebot.kunden` | lesend | öffentlich, Kunden-Wartung | siehe Datei | `app/api/orders.php` |
| `kunde_bestellungen` | `angebot.kunden` | lesend | öffentlich, Kunden-Wartung | siehe Datei | `app/api/orders.php` |
| `kunde_login` | `angebot.kunden` | schreibend | öffentlich, Kunden-Wartung, eigene Anmeldung | – | `app/api/aktionen/kundenportal.php` |
| `kunde_logout` | `angebot.kunden` | schreibend | öffentlich | Kunde | `app/api/aktionen/kundenportal.php` |
| `kunde_mail` | `angebot.eingabe` | schreibend | – | Recht kunden.bearbeiten + Bestätigung | `app/api/aktionen/mail.php` |
| `kunde_merkliste` | `angebot.kunden` | lesend | öffentlich, Kunden-Wartung | Kunde | `app/api/aktionen/kundenportal.php` |
| `kunde_merkliste_save` | `angebot.kunden` | schreibend | öffentlich, Kunden-Wartung | Kunde | `app/api/aktionen/kundenportal.php` |
| `kunde_passwort` | `angebot.kunden` | schreibend | öffentlich, Kunden-Wartung, eigene Anmeldung | Kunde | `app/api/aktionen/kundenportal.php` |
| `kunde_status` | `angebot.kunden` | lesend | öffentlich | Kunde | `app/api/aktionen/kundenportal.php` |
| `kunde_token_check` | `angebot.kunden` | schreibend | öffentlich, Kunden-Wartung, eigene Anmeldung | – | `app/api/aktionen/kundenportal.php` |
| `kunde_token_set` | `angebot.kunden` | schreibend | öffentlich, Kunden-Wartung, eigene Anmeldung | – | `app/api/aktionen/kundenportal.php` |
| `kunden_mail_vorschau` | `angebot.eingabe` | schreibend | – | angemeldet | `app/api/aktionen/mail.php` |
| `kunden_restposten` | `angebot.eingabe` | schreibend | – | Recht sonderposten.senden + Bestätigung | `app/api/aktionen/mail.php` |
| `kunden_rundmail` | `angebot.eingabe` | schreibend | – | Recht wochenangebot.senden + Bestätigung | `app/api/aktionen/mail.php` |
| `mail_info` | `angebot.eingabe` | lesend | – | angemeldet | `app/api/aktionen/mail.php` |
| `offer` | `angebot.kunden` | lesend | öffentlich, Kunden-Wartung | Recht einzelangebote.sehen, Kunde | `app/api/aktionen/angebote.php` |
| `offers` | `angebot.eingabe` | lesend | – | angemeldet | `app/api/aktionen/angebote.php` |
| `offers_save` | `angebot.eingabe` | schreibend | – | Recht angebote.loeschen + Bestätigung, Recht angebote.verwalten | `app/api/aktionen/angebote.php` |
| `publish` | `angebot.eingabe` | schreibend | – | Recht angebot.veroeffentlichen | `app/api/aktionen/entwurf.php` |
| `restposten_info` | `angebot.eingabe` | lesend | – | Recht sonderposten.senden | `app/api/aktionen/mail.php` |
| `save_draft` | `angebot.eingabe` | schreibend | – | Recht angebot.bearbeiten | `app/api/aktionen/entwurf.php` |
| `version` | `angebot.eingabe` | lesend | – | – | `app/api/aktionen/entwurf.php` |
| `versions` | `angebot.eingabe` | lesend | – | – | `app/api/aktionen/entwurf.php` |

## Bestand (`bestand`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `stock` | `angebot.eingabe` | lesend | – | Recht bestand.sehen | `app/api/aktionen/bestand.php` |
| `stock_import` | `angebot.eingabe` | schreibend | – | Recht bestand.importieren | `app/api/aktionen/bestand.php` |
| `stock_mhd_senden` | `angebot.eingabe` | schreibend | – | Recht bestand.mhd_senden | `app/api/aktionen/bestand.php` |
| `stock_pdf` | `angebot.eingabe` | schreibend | – | Recht bestand.sehen | `app/api/aktionen/bestand.php` |

## Leergut (`leergut`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `leergut_abschreibung_save` | `leergut.intern` | schreibend | – | Recht leergut.bearbeiten | `app/api/aktionen/leergut.php` |
| `leergut_abstimmung_save` | `leergut.intern` | schreibend | – | Recht leergut.bearbeiten | `app/api/aktionen/leergut.php` |
| `leergut_bewegung_save` | `leergut.intern` | schreibend | – | Recht leergut.bearbeiten | `app/api/aktionen/leergut.php` |
| `leergut_bewegung_storno` | `leergut.intern` | schreibend | – | Recht leergut.bearbeiten | `app/api/aktionen/leergut.php` |
| `leergut_bilanz` | `leergut.intern` | lesend | – | Recht leergut.sehen | `app/api/aktionen/leergut.php` |
| `leergut_dachser_import` | `leergut.intern` | schreibend | – | Recht leergut.bearbeiten | `app/api/aktionen/leergut.php` |
| `leergut_export` | `leergut.intern` | schreibend | – | Recht leergut.sehen | `app/api/aktionen/leergut.php` |
| `leergut_import` | `leergut.intern` | schreibend | – | Recht leergut.verwalten | `app/api/aktionen/leergut.php` |
| `leergut_inventur_save` | `leergut.intern` | schreibend | – | Recht leergut.bearbeiten | `app/api/aktionen/leergut.php` |
| `leergut_konto` | `leergut.intern` | lesend | – | Recht leergut.sehen | `app/api/aktionen/leergut.php` |
| `leergut_lademittel_save` | `leergut.intern` | schreibend | – | Recht leergut.verwalten | `app/api/aktionen/leergut.php` |
| `leergut_partner_save` | `leergut.intern` | schreibend | – | Recht leergut.verwalten | `app/api/aktionen/leergut.php` |
| `leergut_start` | `leergut.intern` | lesend | – | Recht leergut.sehen | `app/api/aktionen/leergut.php` |
| `leergut_winab_import` | `leergut.intern` | schreibend | – | Recht leergut.verwalten | `app/api/aktionen/leergut.php` |

## CRM (`crm`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `crm_aktivitaet` | `crm.intern` | schreibend | – | Recht crm.bearbeiten | `app/api/aktionen/crm.php` |
| `crm_export` | `crm.intern` | schreibend | – | Recht crm.exportieren | `app/api/aktionen/crm.php` |
| `crm_interessent_save` | `crm.intern` | schreibend | – | Recht crm.bearbeiten | `app/api/aktionen/crm.php` |
| `crm_karte` | `crm.intern` | lesend | – | Recht crm.sehen | `app/api/aktionen/crm.php` |
| `crm_kunde_save` | `crm.intern` | schreibend | – | Recht crm.bearbeiten | `app/api/aktionen/crm.php` |
| `crm_start` | `crm.intern` | lesend | – | Recht crm.sehen | `app/api/aktionen/crm.php` |
| `crm_verlauf` | `crm.intern` | lesend | – | Recht crm.sehen | `app/api/aktionen/crm.php` |

## REWE (`rewe`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `rewe_abschluss` | `rewe.intern` | lesend | – | – | `app/api/aktionen/rewe.php` |
| `rewe_antwort` | `rewe.intern` | schreibend | – | Recht rewe.bearbeiten | `app/api/aktionen/rewe.php` |
| `rewe_dauer_uebernehmen` | `rewe.intern` | schreibend | – | Recht rewe.bearbeiten | `app/api/aktionen/rewe.php` |
| `rewe_erfasst` | `rewe.intern` | schreibend | – | – | `app/api/aktionen/rewe.php` |
| `rewe_export` | `rewe.intern` | schreibend | – | – | `app/api/aktionen/rewe.php` |
| `rewe_import` | `rewe.intern` | schreibend | – | Recht rewe.verwalten | `app/api/aktionen/rewe.php` |
| `rewe_maerkte` | `rewe.intern` | lesend | – | Recht rewe.sehen | `app/api/aktionen/rewe.php` |
| `rewe_markt` | `rewe.intern` | lesend | – | Recht rewe.sehen | `app/api/aktionen/rewe.php` |
| `rewe_markt_save` | `rewe.intern` | schreibend | – | Recht rewe.bearbeiten | `app/api/aktionen/rewe.php` |
| `rewe_notiz_save` | `rewe.intern` | schreibend | – | Recht rewe.bearbeiten | `app/api/aktionen/rewe.php` |
| `rewe_stamm_save` | `rewe.intern` | schreibend | – | Recht rewe.verwalten | `app/api/aktionen/rewe.php` |
| `rewe_start` | `rewe.intern` | lesend | – | Recht rewe.sehen | `app/api/aktionen/rewe.php` |
| `rewe_team_save` | `rewe.intern` | schreibend | – | Recht rewe.verwalten | `app/api/aktionen/rewe.php` |
| `rewe_woche` | `rewe.intern` | lesend | – | Recht rewe.sehen | `app/api/aktionen/rewe.php` |
| `rewe_zuweisen` | `rewe.intern` | schreibend | – | Recht rewe.verwalten | `app/api/aktionen/rewe.php` |

## Einkauf (`einkauf`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `einkauf` | `angebot.eingabe` | lesend | – | Recht einkauf.sehen | `app/api/aktionen/einkauf.php` |
| `einkauf_melden` | `angebot.eingabe` | schreibend | – | Recht einkauf.melden | `app/api/aktionen/einkauf.php` |

## HR (`hr`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `hr_altbestand_zuordnen` | `angebot.eingabe` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `hr_antraege_save` | `angebot.eingabe` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `hr_antrag` | `hr.intern` | schreibend | – | Recht hr.antrag | `app/api/aktionen/hr.php` |
| `hr_antrag_zurueckziehen` | `hr.intern` | schreibend | – | Recht hr.antrag | `app/api/aktionen/hr.php` |
| `hr_einstellungen_save` | `angebot.eingabe` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `hr_eintrag_save` | `hr.intern` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `hr_entscheiden` | `hr.intern` | schreibend | – | Recht hr.genehmigen | `app/api/aktionen/hr.php` |
| `hr_export` | `hr.intern` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `hr_import_pruefen` | `hr.intern` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `hr_import_uebernehmen` | `hr.intern` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `hr_korrektur` | `hr.intern` | schreibend | – | Recht hr.antrag | `app/api/aktionen/hr.php` |
| `hr_korrektur_erledigt` | `hr.intern` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `hr_monat` | `hr.intern` | lesend | – | Recht hr.antrag | `app/api/aktionen/hr.php` |
| `hr_offen` | `hr.intern` | lesend | – | Recht hr.genehmigen | `app/api/aktionen/hr.php` |
| `hr_personal_uebernehmen` | `angebot.eingabe` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `hr_start` | `hr.intern` | lesend | – | Recht hr.antrag | `app/api/aktionen/hr.php` |
| `hr_uebersicht` | `hr.intern` | lesend | – | angemeldet | `app/api/aktionen/hr.php` |
| `hr_verwaltung` | `hr.intern` | lesend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `mitarbeiter_hr` | `angebot.eingabe` | lesend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |
| `mitarbeiter_hr_save` | `angebot.eingabe` | schreibend | – | Recht hr.verwalten | `app/api/aktionen/hr.php` |

## Marketing (`marketing`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `marketing_beitrag_loeschen` | `marketing.intern` | schreibend | – | Recht marketing.verwalten | `app/api/aktionen/marketing.php` |
| `marketing_beitrag_save` | `marketing.intern` | schreibend | – | Recht marketing.bearbeiten | `app/api/aktionen/marketing.php` |
| `marketing_einstellungen_save` | `marketing.intern` | schreibend | – | Recht marketing.verwalten | `app/api/aktionen/marketing.php` |
| `marketing_export` | `marketing.intern` | schreibend | – | Recht marketing.sehen | `app/api/aktionen/marketing.php` |
| `marketing_kampagne_save` | `marketing.intern` | schreibend | – | Recht marketing.bearbeiten | `app/api/aktionen/marketing.php` |
| `marketing_kommentar` | `marketing.intern` | schreibend | – | Recht marketing.bearbeiten | `app/api/aktionen/marketing.php` |
| `marketing_start` | `marketing.intern` | lesend | – | Recht marketing.sehen | `app/api/aktionen/marketing.php` |

## Controlling (`controlling`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `controlling_start` | `controlling.intern` | lesend | – | – | `app/api/aktionen/controlling.php` |
| `controlling_umsatz` | `controlling.intern` | lesend | – | Recht controlling.umsatz_sehen | `app/api/aktionen/controlling.php` |
| `controlling_umsatz_monat_save` | `controlling.intern` | schreibend | – | Recht controlling.umsatz_bearbeiten | `app/api/aktionen/controlling.php` |

## Verwaltung (`verwaltung`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `auswertung` | `angebot.eingabe` | lesend | – | Recht auswertung.sehen | `app/api/aktionen/auswertung.php` |
| `import_arten` | `angebot.eingabe` | lesend | – | angemeldet | `app/api/aktionen/importzentrale.php` |
| `import_pruefen` | `angebot.eingabe` | schreibend | – | – | `app/api/aktionen/importzentrale.php` |
| `import_uebernehmen` | `angebot.eingabe` | schreibend | – | – | `app/api/aktionen/importzentrale.php` |
| `kunde_delete` | `angebot.eingabe` | schreibend | – | Recht kunden.bearbeiten + Bestätigung | `app/api/aktionen/kundenverwaltung.php` |
| `kunde_save` | `angebot.eingabe` | schreibend | – | Recht kunden.bearbeiten + Bestätigung | `app/api/aktionen/kundenverwaltung.php` |
| `kunden` | `angebot.eingabe` | lesend | – | Recht kunden.sehen | `app/api/aktionen/kundenverwaltung.php` |
| `kunden_import` | `angebot.eingabe` | schreibend | – | Recht kunden.bearbeiten + Bestätigung, Recht kunden.bearbeiten | `app/api/aktionen/kundenverwaltung.php` |
| `kundengruppen` | `angebot.eingabe` | lesend | – | – | `app/api/aktionen/kundengruppen.php` |
| `kundengruppen_save` | `angebot.eingabe` | schreibend | – | – | `app/api/aktionen/kundengruppen.php` |
| `master` | `angebot.eingabe` | lesend | – | Recht stammdaten.sehen | `app/api/aktionen/bestand.php` |
| `master_save` | `angebot.eingabe` | schreibend | – | Recht stammdaten.bearbeiten | `app/api/aktionen/bestand.php` |
| `ort_update` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/auswertung.php` |
| `vertreter` | `angebot.eingabe` | lesend | – | angemeldet | `app/api/aktionen/kundengruppen.php` |
| `vertreter_save` | `angebot.eingabe` | schreibend | – | Recht stammdaten.bearbeiten | `app/api/aktionen/kundengruppen.php` |
| `vkgruppen` | `angebot.eingabe` | lesend | – | – | `app/api/aktionen/kundengruppen.php` |
| `vkgruppen_save` | `angebot.eingabe` | schreibend | – | – | `app/api/aktionen/kundengruppen.php` |

## Sicherheit (`sicherheit`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `sicherheit_bericht` | `sicherheit.intern` | lesend | – | angemeldet | `app/api/aktionen/sicherheit.php` |
| `sicherheit_bericht_einstellen` | `sicherheit.intern` | schreibend | – | Administrator | `app/api/aktionen/sicherheit.php` |
| `sicherheit_bericht_senden` | `sicherheit.intern` | schreibend | – | Administrator | `app/api/aktionen/sicherheit.php` |
| `sicherheit_ereignisse` | `sicherheit.intern` | lesend | – | angemeldet | `app/api/aktionen/sicherheit.php` |
| `sicherheit_konten` | `sicherheit.intern` | lesend | – | Administrator | `app/api/aktionen/sicherheit.php` |
| `sicherheit_konto_deaktivieren` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/sicherheit.php` |
| `sicherheit_lage` | `sicherheit.intern` | lesend | – | angemeldet | `app/api/aktionen/sicherheit.php` |
| `sicherheit_leitfaden` | `sicherheit.intern` | schreibend | – | Administrator | `app/api/aktionen/sicherheit.php` |
| `sicherheit_leitfaden_haken` | `sicherheit.intern` | schreibend | – | Recht sicherheit.notfall | `app/api/aktionen/sicherheit.php` |
| `sicherheit_notfall_an` | `sicherheit.intern` | schreibend | – | Recht sicherheit.notfall + Bestätigung | `app/api/aktionen/sicherheit.php` |
| `sicherheit_notfall_aus` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/sicherheit.php` |
| `sicherheit_probe_gesehen` | `sicherheit.intern` | schreibend | – | angemeldet | `app/api/aktionen/sicherheit.php` |
| `sicherheit_probealarm` | `sicherheit.intern` | schreibend | – | Recht sicherheit.notfall | `app/api/aktionen/sicherheit.php` |

## App (iOS/Android) (`mobile`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `app_info` | `angebot.kunden` | lesend | öffentlich | – | `app/api/aktionen/app.php` |

## Plattformkern (`plattform`)

| Aktion | Oberfläche | Art | Kennzeichen | Prüfung im Code | Datei |
| --- | --- | --- | --- | --- | --- |
| `anmeldekonto` | `angebot.eingabe` | lesend | – | Administrator | `app/api/aktionen/anmeldekonten.php` |
| `anmeldekonto_aendern` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/anmeldekonten.php` |
| `anmeldung_pruefen` | `plattform.anmeldung` | lesend | wartungsfrei | – | `app/api/aktionen/zugang.php` |
| `benachrichtigung_save` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/mail.php` |
| `benachrichtigung_test` | `angebot.eingabe` | schreibend | – | Administrator | `app/api/aktionen/mail.php` |
| `betrieb_status` | `sicherheit.intern` | lesend | – | Administrator | `app/api/aktionen/verwaltung.php` |
| `change_password` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/zugang.php` |
| `fw_export` | `sicherheit.intern` | lesend | – | Administrator | `app/api/aktionen/schutz.php` |
| `fw_feed_auffrischen` | `sicherheit.intern` | schreibend | – | Administrator | `app/api/aktionen/schutz.php` |
| `fw_feed_update` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/schutz.php` |
| `fw_freigeben` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/schutz.php` |
| `fw_import` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/schutz.php` |
| `fw_save` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/schutz.php` |
| `fw_sperren` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/schutz.php` |
| `fw_status` | `sicherheit.intern` | lesend | – | Administrator | `app/api/aktionen/schutz.php` |
| `fw_verkehr` | `sicherheit.intern` | lesend | – | Administrator | `app/api/aktionen/schutz.php` |
| `fw_vorlage` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/schutz.php` |
| `geo_clear_stats` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `geo_lookup` | `sicherheit.intern` | lesend | – | Administrator | `app/api/aktionen/verwaltung.php` |
| `geo_update` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `ip_unblock` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `log` | `angebot.eingabe` | lesend | – | Recht protokoll.sehen | `app/api/aktionen/verwaltung.php` |
| `login` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/zugang.php` |
| `login_2fa` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/zugang.php` |
| `logout` | `angebot.eingabe` | schreibend | wartungsfrei | – | `app/api/aktionen/zugang.php` |
| `mail_konto_save` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/mail.php` |
| `mail_save` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/mail.php` |
| `mail_status` | `angebot.eingabe` | lesend | – | Administrator | `app/api/aktionen/mail.php` |
| `mail_test` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/mail.php` |
| `modul_freigabe_save` | `sicherheit.intern` | schreibend | – | siehe Datei | `app/api/aktionen/module.php` |
| `modul_tester_save` | `sicherheit.intern` | schreibend | – | siehe Datei | `app/api/aktionen/module.php` |
| `modul_wartung_save` | `sicherheit.intern` | schreibend | – | siehe Datei | `app/api/aktionen/module.php` |
| `module_status` | `angebot.eingabe` | lesend | wartungsfrei | siehe Datei | `app/api/aktionen/module.php` |
| `passkey_begin` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/passkey.php` |
| `passkey_delete` | `angebot.eingabe` | schreibend | eigene Anmeldung | angemeldet | `app/api/aktionen/passkey.php` |
| `passkey_list` | `angebot.eingabe` | lesend | – | angemeldet | `app/api/aktionen/passkey.php` |
| `passkey_login` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/passkey.php` |
| `passkey_login_begin` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/passkey.php` |
| `passkey_register` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/passkey.php` |
| `passkey_rename` | `angebot.eingabe` | schreibend | eigene Anmeldung | angemeldet | `app/api/aktionen/passkey.php` |
| `reauth` | `angebot.eingabe` | schreibend | eigene Anmeldung | angemeldet | `app/api/aktionen/zugang.php` |
| `rechte` | `angebot.eingabe` | lesend | – | Administrator | `app/api/aktionen/verwaltung.php` |
| `rechte_save` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `rolle_loeschen` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `rolle_save` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `security_diag` | `sicherheit.intern` | schreibend | – | Administrator | `app/api/aktionen/verwaltung.php` |
| `security_export` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `security_integrity` | `sicherheit.intern` | post | – | siehe Datei | `app/api/aktionen/integritaet.php` |
| `security_save` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `security_status` | `sicherheit.intern` | lesend | – | Administrator | `app/api/aktionen/verwaltung.php` |
| `session_end` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `setup` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/zugang.php` |
| `status` | `angebot.eingabe` | lesend | wartungsfrei | – | `app/api/aktionen/zugang.php` |
| `testpostfach` | `angebot.eingabe` | lesend | – | Administrator | `app/api/aktionen/mail.php` |
| `theme_save` | `angebot.eingabe` | schreibend | wartungsfrei | angemeldet | `app/api/aktionen/zugang.php` |
| `twofa_begin` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/zugang.php` |
| `twofa_disable` | `angebot.eingabe` | schreibend | eigene Anmeldung | angemeldet | `app/api/aktionen/zugang.php` |
| `twofa_enable` | `angebot.eingabe` | schreibend | wartungsfrei, eigene Anmeldung | – | `app/api/aktionen/zugang.php` |
| `user_delete` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `user_mail` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `user_save` | `angebot.eingabe` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `user_unlock` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/verwaltung.php` |
| `users` | `angebot.eingabe` | lesend | – | Administrator | `app/api/aktionen/verwaltung.php` |
| `waf_probe` | `angebot.kunden` | lesend | öffentlich | – | `app/api/aktionen/schutz.php` |
| `wartung_save` | `sicherheit.intern` | schreibend | – | Administrator + Bestätigung | `app/api/aktionen/zugang.php` |
