# App „Standard-Fleisch“ (iOS und Android)

Eine App für Kunden und Mitarbeiter, gebaut mit Expo (React Native, TypeScript). Sie nutzt die Schnittstelle
des Portals ([docs/app-api.md](../docs/app-api.md)); Preise, Fracht und Rechte prüft nur der Server.

## Was die App kann

**Kunden und Gäste**
- Angebot wie auf der Website: Gruppen, Bereiche, Suche (Name, Nummer, Merkmal), Sonderposten, Vermerk mit Fracht.
- Mehrere freigeschaltete Angebote je Kunde, Auswahl oben.
- Merkliste: für angemeldete Kunden mit der Website abgeglichen (gleiche Schlüssel aus `app/assets/offer-core.js`),
  für Gäste auf dem Gerät; beim ersten Anmelden übernommen.
- Bestellwunsch: Menge je Artikel (mit +5/+10/+25 kg), Leiste mit Summe, Prüfseite mit Frachtanteil unter der
  Mindestmenge, Wunschtermin, Referenz, Bemerkung. Jede Übermittlung trägt eine Kennung (`requestId`): bricht die
  Verbindung ab, entsteht beim erneuten Senden kein zweiter Bestellwunsch. Der Entwurf bleibt auf dem Gerät.
- „Meine Bestellwünsche“ mit Bearbeitungsstand und Details.
- Ohne Netz: zuletzt geladenes Angebot mit Hinweis „Preise ohne Gewähr“; Senden erst wieder online.
- Konto: Passwort ändern (auch Pflichtwechsel beim ersten Anmelden), Abmelden, Kontakt/Impressum/Datenschutz.

**Mitarbeiter** (Zugang zum Eingabebereich, mit Zwei-Faktor-Code)
- Bestellwünsche: Suche, Status-Filter, seitenweise; Detail mit Kundendaten (Anrufen/E-Mail), Positionen, Verlauf.
- Status, Zuständigkeit und interne Notiz ändern (nur mit Recht „Bestellwünsche bearbeiten“). Hat jemand anderes
  inzwischen geändert, überschreibt die App nichts (Revision, HTTP 409).

Angebote pflegen, Kunden und Einstellungen bleiben im Eingabebereich der Website.

## Entwickeln und prüfen

```
cd mobile
npm ci
npm run typecheck        # TypeScript
npm test                 # Unit-Tests (tests/kern.test.ts)
npm run export:native    # iOS- und Android-Bundle erzeugen (prüft, dass die App für beide Plattformen baut)
npm run export:web       # Web-Build für die Ende-zu-Ende-Tests (python3 tests/run_e2e.py app_web)
npm start                # Entwicklungsserver (Expo Go / Simulator)
```

Die Ende-zu-Ende-Gruppe `app_web` testet den Web-Build der App gegen einen echten PHP-Testserver (beide
Speicherarten). Das Verhalten auf echten Geräten (Tastatur, Schlüsselbund, Systemdialoge) prüft sie nicht – dafür
die Vorschau-Builds unten auf einem iPhone und einem Android-Gerät ausprobieren.

Die CI prüft all das bei jedem Pull Request im Auftrag „App prüfen (iOS, Android, Web)“: Typprüfung, Unit-Tests,
Bundles für iOS und Android, Web-Build und `app_web` in beiden Speicherarten.

**Server wählen:** In der App siebenmal auf die Versionsnummer (Konto) tippen → „Server“: Echtbetrieb oder
Testumgebung. Benutzer und Passwort der Testumgebung gibt man dort am Gerät ein; sie liegen nur im sicheren
Speicher des Geräts und nie im Quellcode.

## Veröffentlichen (Schritte für den Inhaber)

Die Veröffentlichung ist bewusst **nicht** automatisiert und läuft getrennt vom Server-Release.

1. Konten anlegen: [Expo](https://expo.dev) (kostenlos), Apple Developer Program (jährliche Gebühr) und Google
   Play Console (einmalige Gebühr). Zugangsdaten nur dort bzw. im eigenen Passwortmanager, nie im Repository.
2. Einmalig: `npx eas-cli@latest login` und `npx eas-cli@latest init` im Ordner `mobile/` (trägt die Projekt-ID
   in `app.json` ein – als Pull Request übernehmen).
3. Probeversion für eigene Geräte: `npx eas-cli@latest build --profile vorschau --platform android` (installierbare
   APK) bzw. `--platform ios` (Gerät vorher in EAS registrieren).
4. Store-Version: `npx eas-cli@latest build --profile produktion --platform all`, dann
   `npx eas-cli@latest submit --profile produktion`. Signierschlüssel verwaltet EAS; nichts davon gehört ins Repository.
5. Store-Angaben: Name „Standard-Fleisch“, Kennung `de.standardfleisch.angebot`, Datenschutzerklärung
   `https://angebot-stafl.de/datenschutz/` (vorher um die App ergänzen lassen). Für die Datenschutzangaben der Stores:
   Benutzername/Passwort zur Anmeldung, Bestellwünsche und Kontaktdaten des Kunden, ungefährer Ort der Anmeldung
   aus der IP-Adresse (Auswertung), keine Werbung, kein Tracking, keine Weitergabe.
6. Für die Prüfung durch Apple/Google einen Test-Kundenzugang bereitstellen (nur mit Testdaten).

Neue Versionen: `version` in `app.json` erhöhen (bei iOS zusätzlich `buildNumber`, bei Android `versionCode`),
dann Schritte 4–5. Muss eine alte App gesperrt werden, `APP_MIN_VERSION` in `app/api/aktionen/app.php` erhöhen
(über den normalen Release, erst wenn die neue Version in beiden Stores verfügbar ist).

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `src/app/` | Seiten (Expo Router): `(kunde)/` Angebot, Merkliste, Bestellen, Meine, Konto; `(team)/` Bestellwünsche, Konto; `artikel/[id]`, `kunde-bestellung/[nr]`, `vorgang/[nr]`, `anmelden`, `mitarbeiter`, `server` |
| `src/kern/` | Logik ohne Oberfläche: `api.ts` (Verbindung, Sitzung, Fehler), `angebot.ts`, `bestellung.ts`, `status.ts`, `version.ts`, `speicher.ts` |
| `src/zustand/` | `sitzung.tsx` (Server, Anmeldung, Grunddaten), `angebot.tsx` (Angebot, offline, Merkliste, Entwurf, Senden) |
| `src/ui/` | Bausteine, Farben wie die Website (hell/dunkel), Artikelzeile, Bestellwunsch-Anzeige |
| `tests/` | Unit-Tests (Jest) |

Hinweis zu `npm audit`: Die gemeldeten Lücken liegen in Werkzeugen von Expo/Metro für den Build (z. B. `braces`,
`node-forge`, `uuid` in den Konfigurationswerkzeugen), nicht im ausgelieferten App-Code. Bei Expo-Updates mit
`npx expo install --fix` aktualisieren.
