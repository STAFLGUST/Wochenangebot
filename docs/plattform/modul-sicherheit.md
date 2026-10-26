# Modul Sicherheit (sicherheit.dashboard-stafl.de)

Stand 26.10.2026 · Auftrag des Inhabers vom 26.10.2026 („die Punkte als ein Modul im Dashboard, Aufbau überdenken,
Notfall-Knopf, der wirklich etwas bewirkt, als Berechtigung zuweisbar, Kachel unten rechts neben Verwaltung“) ·
Freigabe des Inhabers für eigene Adresse, eigenen Keycloak-Client und produktive Kachel mit dem Merge (26.10.2026).

## 1. Ausgangslage und Ziel

Bisher lagen die Sicherheitsfunktionen im Eingabebereich unter **Verwaltung → Sicherheit** und **Verwaltung → Schutz**: eine
lange Seite mit Lagebild, Konfigurationsprüfung, Diagnose, Dateiprüfung, Wartungsmodus, Modulverwaltung, Einstellungen,
Passwortbestätigung, Länderstatistik, Sitzungen, Sperren und Fehlversuchen – daneben die Schutzzentrale (Firewall, Live-Verkehr,
Sperrliste, Vorlagen). Betrieb (Wartung, Module, Systemzustand) und Sicherheit waren vermischt, und der Bereich war nur auf dem
gemeinsamen Eingabebereich erreichbar.

Ziel: ein eigenes Modul **Sicherheit** auf eigener Adresse mit klarer Gliederung, einem echten **Notfallmodus** und sauberer
Trennung zur Verwaltung. Die Dienste dahinter (Einstellungen, Firewall, Dateiprüfung, Sitzungen, Protokoll) bleiben im
Plattformkern – das Modul ist ihre Oberfläche. Es gibt **keine zweite Logik**: Der Notfallmodus nutzt die vorhandene
Wartungs-Entscheidungstabelle (GR-102/GR-107), die vorhandene Sitzungsverwaltung und die vorhandene Firewall-Vorlage.

## 2. Aufbau (Reiter)

Hauptansichten bleiben schlank (Lage, Listen, Zustände); Details, Bearbeiten und Bestätigungen öffnen sich in Dialogen
(auf dem Handy als Blatt von unten, Esc/Schließen, Fokus zurück auf den auslösenden Knopf, keine verschachtelten Dialoge).

| Reiter | Inhalt | Wer |
|---|---|---|
| **Lagebild** | Gesamtbewertung, Notfall-Zustand, Kennzahlen (Angriffe/Abweisungen 24 h, Fehlanmeldungen, gesperrte Adressen, Sitzungen, Zwei-Faktor, Dateiprüfung, Sicherung, Bereitstellung), Verlauf 14 Tage, auffällige Adressen, Konfigurationsprüfung (Server und Browser), letzte Ereignisse | Administrator, `sicherheit.sehen` |
| **Notfall** | Zustand, Wirkungen, Auslösen (mehrstufiger Dialog), Beenden (nur Administrator), letzte Notfälle | `sicherheit.notfall`, Administrator; `sicherheit.sehen` nur Zustand |
| **Firewall & Sperren** | Firewall-Einstellungen, Live-Verkehr, Sperrliste (sperren/freigeben im Dialog), IP-Sperren der Anmeldebremse, Länderstatistik | Administrator |
| **Anmeldung & Sitzungen** | aktive Sitzungen (beenden mit Rückfrage), gesperrte Zugänge, Fehlanmeldungen 7 Tage, Zugänge ohne Zwei-Faktor | Administrator |
| **Dateiprüfung** | letzter Lauf, Befunde (Details im Dialog), Komponenten, „Jetzt prüfen“ | Administrator |
| **Ereignisse** | Sicherheitsprotokoll mit Filter (Art, Zeitraum, Suche), Details im Dialog, CSV-Export | Administrator, `sicherheit.sehen` |
| **Einstellungen & Vorlagen** | Vorlagen Standard · Streng · **Notfall** (Vorschau der Änderungen im Dialog; „Notfall“ startet den Notfallmodus), Export/Import, Anmeldung und Passwörter, IP-Freigabe, Ländersperre, Passwortbestätigung | Administrator |
| **Privilegierte Konten** | Administratoren und Inhaber sicherheitsrelevanter Rechte mit Zwei-Faktor/Passkey, letzter Anmeldung, Sitzungen, Sperre; Details im Dialog | Administrator |

In der **Verwaltung** bleibt nur, was zum Betrieb gehört: Ansicht **System** (Systemzustand, Diagnose, Wartungsmodus der
Angebotsseite, Wartung des Eingabebereichs, Module & Freigaben) und ein Hinweis mit Link zum Modul Sicherheit. Die Ansicht
„Schutz“ entfällt dort. Benutzer, Rollen und Rechte bleiben in der Verwaltung.

## 3. Rechte

| Recht | Bedeutung | Standardrollen |
|---|---|---|
| `sicherheit.zugang` | Kachel und Modul öffnen (automatisch aus dem Register) | **keine** (Registerfeld `zugang_rollen = []`) |
| `sicherheit.sehen` | Lagebild, Ereignisse und Notfall-Zustand nur lesen | keine |
| `sicherheit.notfall` | Notfallmodus **auslösen** | keine |

Administratoren haben immer alle Rechte. Einstellungen, Firewall, Sitzungen, Sperren, Dateiprüfung und das **Beenden** des
Notfalls bleiben fest den Administratoren vorbehalten (GR-103, `PERMS_ADMIN_ONLY`). Wer `sicherheit.notfall` hat, bekommt
`sicherheit.zugang` automatisch als Voraussetzung. Begründung für „Beenden nur Administrator“: Ein Notfall soll von vielen
vertrauenswürdigen Personen schnell ausgelöst, aber nur nach Prüfung durch einen Administrator beendet werden – ein
übernommenes Konto mit diesem Recht kann den Notfall damit nicht aufheben.

## 4. Notfallmodus

Auslösen: Dialog in drei Schritten – (1) Wirkungen ansehen, (2) Grund, optionaler Kundenhinweis, Optionen und das
Bestätigungswort `NOTFALL`, (3) Bestätigung durch erneute Anmeldung (Katalog `BESTAETIGUNG`, Schlüssel `notfall_ausloesen`,
abschaltbar; Beenden `notfall_beenden`, immer mit Bestätigung). Aktion `sicherheit_notfall_an` bzw. `sicherheit_notfall_aus`.

Wirkungen (alle serverseitig):

1. **Kunden** sehen auf angebot-stafl.de den Wartungshinweis (neutraler Text, kein Hinweis auf einen Sicherheitsvorfall);
   Kundenfunktionen antworten mit 503 – über `wartung()`, also genau wie beim Wartungsmodus (GR-009). Angemeldete Mitarbeiter
   ohne Administratorrolle kommen dort nicht mehr an der Wartung vorbei.
2. **Mitarbeiter ohne Administratorrolle** sind ausgesperrt: Jede sperrbare interne Oberfläche (Angebot, Bestand, Verwaltung,
   Import, HR, CRM, Marketing …) gilt als „in Wartung“; die Entscheidungstabelle (`regeln/wartung.toml`) antwortet mit 503,
   Administratoren arbeiten weiter (Regel 5). Nicht sperrbar bleiben Dashboard, zentrale Anmeldung und das Modul Sicherheit
   (dort sehen Inhaber von `sicherheit.notfall`/`sicherheit.sehen` den Zustand).
3. **Sitzungen**: alle Kundensitzungen und alle Mitarbeitersitzungen ohne Administratorrolle werden beendet; optional auch die
   anderer Administratoren (außer der eigenen) und – wenn die Kontenverwaltung der zentralen Anmeldung eingerichtet ist – die
   Keycloak-Sitzungen der betroffenen Konten. Hinweis: Auf Keycloak-Hosts entsteht nach erneuter Anmeldung wieder eine
   Sitzung; die Sperre selbst ist die 503-Antwort aus Punkt 2, nicht das Abmelden.
4. **E-Mail-Versand pausiert** (zentral in `mail_send_many`): Rundmails, Einzelangebote, Kunden-E-Mails, Bestellmails,
   Zugangsdaten. Ausnahme: Benachrichtigungen an die eingetragenen Empfänger (Sicherheitsereignisse). Fehlgeschlagene
   Bestellmails lassen sich danach wie gewohnt nachsenden.
5. **Firewall** auf Vorlage „Notfall“ (Sperre ab dem ersten Treffer für 7 Tage, Bedrohungsliste, Mitschnitt 60 Minuten,
   Zwei-Faktor für alle, kurze Sitzungen). Die vorherigen Einstellungen werden im Notfall-Dokument gesichert und beim Beenden
   wiederhergestellt (abwählbar: strenge Einstellungen behalten).
6. **Benachrichtigung** sofort (ohne Bündelpause) an die Empfänger der Sicherheitsereignisse und Eintrag im Protokoll
   (Vorgang `notfall`, auch im Sicherheitsprotokoll-Export).

Bewusst **nicht** betroffen: Datensicherung und andere Hintergrundläufe, Administratoren, Lesen der Daten. Importe und
Schreibaktionen pausieren über Punkt 2 (nur Administratoren können noch etwas ändern, z. B. Daten wiederherstellen).

Beenden: im Modul (Administrator, erneute Anmeldung) oder auf dem Server mit `sh deploy/notfall-aus.sh` – stellt auch die
gesicherten Firewall- und Sicherheitseinstellungen wieder her (für den Fall, dass die strenge Firewall die eigene Adresse
gesperrt hat). Danach Mitarbeiter wieder normal; eine vorher von Hand eingeschaltete Wartung bleibt bestehen.

Dokument `sicherheit-notfall` (Eigentümer `plattform`): `aktiv`, `seit`, `von`, `vonName`, `grund`, `kundentext`,
`optionen`, `wirkung` (Zahlen), `vorher` (`sicherheit`, `firewall`), `verlauf` (letzte 20 Notfälle ohne Schnappschüsse).

## 5. Technik

- Register: Modul `sicherheit` (Kachel 81, Gruppe `verwaltung`, also unten rechts neben der Verwaltung), Oberfläche
  `sicherheit.intern` = `https://sicherheit.dashboard-stafl.de/module/sicherheit/`, fertig/produktiv, **nicht sperrbar**
  (die Sicherheitszentrale darf sich nie selbst aussperren).
- Aktionen auf `sicherheit.intern` (GR-109: nur auf diesem Host): die bisherigen `security_*`, `fw_*` (außer `waf_probe`),
  `geo_*`, `session_end`, `ip_unblock`, `user_unlock` (Code bleibt im Plattformkern, `regeln/aktionen/plattform.toml`) und die
  neuen `sicherheit_*` (`app/api/aktionen/sicherheit.php`, `regeln/aktionen/sicherheit.toml`). Die Verwaltung nutzt für die
  Ansicht System die neue Aktion `betrieb_status` und weiterhin `security_diag`.
- Notfall-Dienst: `app/api/lib/notfall.php`; Haken in `wartung()` (lib/sicherheit.php), `modul_wartung_eintrag()`
  (lib/module.php), Kundenprüfung im API-Einstieg, `mail_send_many()` (lib/kundenmail.php).
- Oberfläche: `app/module/sicherheit/` (eigene Seite wie HR/CRM/Marketing, Hell/Dunkel am Konto, ohne Inline-Skripte).
- Inbetriebnahme: Caddy-Host, Apache-vhost mit `WA_OBERFLAECHE sicherheit.intern`, Keycloak-Client `sicherheit`
  (`konten.sh realm-aktualisieren`, Stand 9), Geheimnisse `OIDC_SECRET_SICHERHEIT`/`OIDC_CRYPTO_SICHERHEIT` über
  `einrichten.sh`. DNS-Eintrag `sicherheit` (CNAME) hat der Inhaber am 26.10.2026 angelegt.

## 6. Risiken und Alternativen

- **Selbstaussperrung**: Die Notfall-Firewall kann die eigene Adresse sperren. Gegenmittel: Büroadresse unter „nie sperren“,
  Server-Werkzeug `deploy/notfall-aus.sh` (stellt die Einstellungen wieder her), `deploy/ip-freigabe-aus.sh`.
- **Missbrauch des Knopfs** (Störung des Betriebs): nur mit eigenem Recht, Bestätigungswort, erneuter Anmeldung, Protokoll und
  sofortiger Benachrichtigung; Beenden nur durch Administratoren.
- **Alternative „Notfall = alle Abmelden“** verworfen: Auf Keycloak-Hosts meldet die zentrale Anmeldung sofort wieder an;
  wirksam ist nur die serverseitige Sperre je Oberfläche.
- **Alternative „eigene Sperrlogik je Modul“** verworfen: doppelte Logik; die Entscheidungstabelle gilt bereits überall.

## 7. Folgearbeiten (eigene Pull Requests)

Probealarm (Notfall üben ohne Wirkung), Leitfaden für den Ernstfall, wöchentlicher Sicherheitsbericht, Erkennung ungenutzter
Konten, Design-Feinschliff.
