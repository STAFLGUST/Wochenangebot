# Inbetriebnahme: Externe Kopie der Datensicherung (Hetzner Storage Box)

Stand 17.11.2026. Die täglichen Sicherungen liegen bisher nur auf demselben Server (`/opt/wochenangebot/sicherungen/`).
Fällt der Server aus, wird er verschlüsselt oder wird das Hostinger-Konto übernommen, sind Daten und Sicherungen
gleichzeitig weg. Diese Anleitung richtet eine zweite, verschlüsselte Kopie bei einem anderen Anbieter ein
(Entscheidung des Inhabers 17.11.2026: Hetzner Storage Box, getrennt von Hostinger und bunny.net).

Die Anleitung enthält keine Adressen und keine Zugangsdaten. `<Benutzer>` ist ein Platzhalter für den Zugang der
Storage Box (Form `u123456-sub1`).

**Kennzeichnung der Schritte**

- **getestet** – so ausgeführt und geprüft: lokal und in der CI mit echtem restic (`tests/deploy/test_sicherung_extern.sh`,
  restic 0.12.1, 0.16.4 und 0.18.1), über den SFTP-Weg mit dem echten `sftp-server` von OpenSSH hinter einer Attrappe für `ssh`.
- **abgeleitet, nicht getestet** – aus der Dokumentation von Hetzner (gelesen am 17.11.2026) und von restic hergeleitet.
  Am Hetzner-Konto, an einer echten Storage Box, am Server und mit systemd wurde für diese Anleitung **nichts** ausgeführt.

## 1. Was eingerichtet wird

- `deploy/sicherung-extern.sh` kopiert den Ordner `sicherungen/` mit **restic** auf die Storage Box: verschlüsselt (das
  Passwort verlässt den Server nie), inkrementell (nur neue Inhalte werden übertragen) und über **SFTP auf Port 23** mit einem
  eigenen SSH-Schlüssel. Das Passwort der Storage Box kennt das Skript nie.
- Kopiert wird, was `deploy/sichern.sh` schon geprüft hat: Archive `daten-`/`intern-<Zeit>.tar.gz`, Abzüge der Anmeldung
  `anmeldung-<Zeit>.dump` und die Stände der Dateiablage `dateien/<Zeit>/`. `sichern.sh` bleibt unverändert.
- Ein eigener Timer startet die Kopie **täglich um 03:30 Uhr**, eine Stunde nach der Sicherung von 02:30 Uhr. Läuft die
  Sicherung noch, wartet die Kopie bis zu 10 Minuten.
- **Aufbewahrung** auf der Storage Box: je Tag ein Stand für 30 Tage, je Woche einer für 8 Wochen, je Monat einer für
  12 Monate. Jeder Stand enthält den ganzen Ordner `sicherungen/`, also schon bis zu 30 Tage lokale Sicherungen. Die externe
  Kopie reicht damit rund **13 Monate** zurück (lokal: 30 Tage). Siehe Abschnitt 8, Punkt „Löschfristen“.
- Unter **Sicherheit → System** zeigt die Karte **„Externe Kopie“** den Zustand: „nicht eingerichtet“, „aktuell – zuletzt
  erfolgreich am …“, „Fehler“, „veraltet“ (letzter erfolgreicher Lauf älter als 36 Stunden) oder „Zeit unklar“ (seine Zeit
  liegt in der Zukunft – Uhr des Servers prüfen). Dieselbe Angabe steht in der Konfigurationsprüfung im Lagebild
  („Externe Datensicherung“). **Die Karte ist ein Hinweis, kein Beleg** (Abschnitt 4, „Grenzen“): Der Beleg ist
  `status` bzw. `pruefen` als root auf dem Server.

## 2. Bei Hetzner (alles *abgeleitet, nicht getestet*)

1. **Storage Box bestellen** in der Hetzner Console. Die kleinste Größe (1 TB) reicht für den Anfang; Standort in
   Deutschland wählen. Konto mit eigenem, starkem Passwort und zweitem Faktor – es darf **nicht** dasselbe Passwort und
   nicht derselbe Mail-Zugang wie bei Hostinger sein, sonst ist die Trennung der Anbieter nur scheinbar.
2. **Vertrag zur Auftragsverarbeitung (AVV)** mit Hetzner abschließen (im Kundenkonto). Die Kopie ist verschlüsselt, enthält
   aber personenbezogene Daten (Personal, Kunden); Hetzner gehört danach ins Verzeichnis der Verarbeitungstätigkeiten.
3. **SSH-Zugang einschalten:** in der Storage Box unter „Einstellungen ändern“ den **SSH-Support** aktivieren (Port 23).
   Andere Zugänge (Samba, WebDAV) bleiben aus. Nach dem Einschalten dauert es einige Minuten, bis der Zugang antwortet.
4. **Unterkonto anlegen** (Sub-Account) nur für diese Kopie, mit eigenem Ordner (z. B. `stafl`) und eigenem Passwort.
   Für das Unterkonto ebenfalls nur SSH einschalten. Das Unterkonto sieht nur seinen Ordner. Benutzer und Adresse haben
   die Form `<Benutzer>@<Benutzer>.your-storagebox.de` – diese Angabe kommt in Schritt 3.1 in die `.env`.
5. **Automatische Snapshots einschalten** (Storage Box → Snapshots → automatische Snapshots, täglich, so viele wie der
   Tarif zulässt). **Das ist der Löschschutz, nicht das Skript:** Wer den Server übernimmt, hat SSH-Schlüssel und
   Repository-Passwort und kann die Kopie auf der Storage Box löschen oder überschreiben. Snapshots legt Hetzner an; über
   den SFTP-Zugang sind sie laut Hetzner-Doku nur lesbar (Verzeichnis `/.zfs/snapshot`).
   Gelöscht werden sie nur in der Hetzner Console – deshalb Schritt 1 (eigenes Passwort, zweiter Faktor).
   Snapshots belegen Platz auf der Storage Box, sobald sich Dateien ändern.
6. Nach dem ersten Lauf (Abschnitt 3) in der Hetzner Console nachsehen, dass ein Snapshot entstanden ist.

Quellen: Hetzner Docs „Storage Box“ (Allgemein, SSH-Keys hinzufügen, Snapshots, Zugriff mit SSH/rsync/BorgBackup).

## 3. Auf dem Server (Hostinger-Browserkonsole, als root)

Ausgehende Verbindungen sind erlaubt; an Firewall, Netzsperre und SSH von außen ändert sich nichts.

1. **Ziel eintragen** (*abgeleitet*): in `/opt/wochenangebot/.env` die Zeile ergänzen

   ```
   SICHERUNG_EXTERN_ZIEL=<Benutzer>@<Benutzer>.your-storagebox.de
   ```

2. **restic installieren** (*abgeleitet*; in der CI genau so aus dem Ubuntu-Archiv installiert):

   ```
   apt-get update && apt-get install -y restic
   restic version
   ```

   Geprüft sind restic 0.12.1 (Ubuntu 22.04), 0.16.4 (Ubuntu 24.04) und 0.18.1 (Ubuntu 26.04).
3. **Einrichten, erster Aufruf** (*getestet* bis auf die echte Verbindung):

   ```
   cd /opt/wochenangebot && sh deploy/sicherung-extern.sh einrichten
   ```

   Der Aufruf erzeugt den SSH-Schlüssel und das Passwort des Repositorys und zeigt:
   - das **Passwort des Repositorys – nur dieses eine Mal**. Sofort in den Passwortmanager übernehmen **und** ausdrucken
     (Ausdruck in den Tresor bzw. zu den Firmenunterlagen). Ohne dieses Passwort ist die externe Kopie wertlos; es liegt
     sonst nur auf dem Server, der im Ernstfall weg ist. Es enthält keine verwechselbaren Zeichen (kein 0/O, 1/l/I).
     **Die Ausgabe nicht kopieren oder weitergeben** – auch nicht in einen Chat, eine E-Mail oder ein Bildschirmfoto.
     Ist das doch geschehen: Passwort wechseln (Abschnitt 4).
   - den öffentlichen Schlüssel und den Befehl zum Hinterlegen,
   - den **Fingerabdruck der Storage Box** (*abgeleitet*): Schon dieser erste Aufruf nimmt Kontakt auf und merkt sich
     den Schlüssel der Gegenstelle ungefragt in `.sicherung-extern-hosts`; ändert er sich später, verweigert die Kopie
     die Verbindung. **Jetzt vergleichen, bevor in Schritt 4 das Passwort des Unterkontos getippt wird:** Der gezeigte
     Fingerabdruck (`SHA256:…`, Zeile mit `ED25519`) muss in der Liste stehen, die Hetzner veröffentlicht –
     [Hetzner Docs, Storage Box Overview, Abschnitt „SSH host keys“](https://docs.hetzner.com/storage/storage-box/general/)
     (gelesen am 17.11.2026). Weicht er ab: abbrechen, `rm /opt/wochenangebot/.sicherung-extern-hosts`, nichts eintippen
     und klären. Zeigt der Aufruf keinen Fingerabdruck, war die Storage Box nicht erreichbar (Schritt 2.3 abwarten,
     Aufruf wiederholen).

   Der erste Aufruf endet mit „Repository nicht erreichbar … Schlüssel hinterlegt?“ – das ist richtig, der Schlüssel
   ist noch nicht hinterlegt.
4. **Öffentlichen Schlüssel in der Storage Box hinterlegen** (*abgeleitet*, Befehl aus der Hetzner-Doku): den vom Skript
   gezeigten Befehl ausführen, in der Form

   ```
   cat /opt/wochenangebot/.sicherung-extern-schluessel.pub | ssh -p 23 -o UserKnownHostsFile=/opt/wochenangebot/.sicherung-extern-hosts <Benutzer>@<Benutzer>.your-storagebox.de install-ssh-key
   ```

   Der Befehl fragt nach dem **Passwort des Unterkontos** (wird nicht angezeigt). Es wird nur hier einmal getippt und
   auf dem Server nicht gespeichert; es muss auch nirgends aufbewahrt werden – für eine Rücksicherung wird es in der
   Hetzner Console neu gesetzt (Schritt 6.3). Eine Rückfrage zum Fingerabdruck kommt hier nicht mehr: Der Schlüssel der
   Gegenstelle ist seit Schritt 3 gemerkt, deshalb der Vergleich dort. Fragt ssh doch „Are you sure you want to continue
   connecting?“ (Schritt 3 hatte keinen Kontakt), den dort gezeigten Fingerabdruck genauso vergleichen und erst dann mit
   `yes` bestätigen.
5. **Einrichten, zweiter Aufruf** (*getestet* über den SFTP-Weg mit `sftp-server`):

   ```
   sh deploy/sicherung-extern.sh einrichten
   ```

   Jetzt legt das Skript das Repository im Ordner `wochenangebot` an und richtet den Timer ein. Das Passwort wird nicht
   erneut angezeigt. Ein weiterer Aufruf ändert nichts.
6. **Erste Übertragung** (*getestet* lokal; Dauer auf dem Server *nicht gemessen*):

   ```
   sh deploy/sicherung-extern.sh jetzt
   ```

   Die erste Übertragung kopiert alles (mit der Dateiablage des QM-Systems können das viele GB sein und Stunden dauern);
   danach nur noch Neues. Bricht die Konsole ab, läuft der Timer in der Nacht weiter – schon übertragene Teile bleiben.
7. **Prüfen** (*getestet*):

   ```
   sh deploy/sicherung-extern.sh status     # Ziel, Timer, Zahl, Alter und Größe der Stände – direkt aus dem Repository
   sh deploy/sicherung-extern.sh pruefen    # restic check + Rücksicherungsprobe
   ```

   `pruefen` holt das neueste Archiv `daten-<Zeit>.tar.gz` von der Storage Box in einen Wegwerf-Ordner zurück und
   vergleicht es byteweise mit dem lokalen Original. Besteht die Prüfung, ändert sie die Karte nicht (ein Fehler des
   letzten Laufs bleibt dort stehen, bis ein Lauf gelingt); scheitert sie, zeigt die Karte den Fehler. Danach unter
   Sicherheit → System die Karte „Externe Kopie“ ansehen.
8. **Optional: Totmannschalter** wie bei der Sicherung: `HC_SICHERUNG_EXTERN_URL=https://…` in `.env` (*abgeleitet*,
   gleiche Bauart wie `HC_SICHERUNG_URL`).

## 4. Laufender Betrieb

- **Täglich:** nichts zu tun. Die Karte „Externe Kopie“ wird gelb bei Fehler oder wenn der neueste Stand älter als
  36 Stunden ist.
- **Monatlich** (Empfehlung): `sh deploy/sicherung-extern.sh pruefen` und in der Hetzner Console nachsehen, dass
  Snapshots entstehen.
- **Ausschalten:** `sh deploy/sicherung-extern.sh aus` entfernt nur den Timer. Repository, Schlüssel und Passwort
  bleiben; die Karte wird nach 36 Stunden gelb („veraltet“). Wieder an: `einrichten`.
- **Dateien auf dem Server** (nur root, nie in `daten/`, nie in den Sicherungen): `.sicherung-extern-schluessel`(+`.pub`),
  `.sicherung-extern-passwort`, `.sicherung-extern-hosts`, `.sicherung-extern-cache/`.
- **Last:** Jeder neue Stand der Dateiablage wird einmal vollständig gelesen (Prüfsummen), übertragen wird nur, was die
  Storage Box noch nicht hat. Der Lauf hat niedrige Priorität (`Nice`, `IOSchedulingClass=idle`).

### Passwort des Repositorys wechseln (*getestet* lokal und über den SFTP-Weg; an der echten Storage Box *nicht getestet*)

**Wann:** Das Passwort ist an eine Stelle geraten, an die es nicht gehört (Chat, E-Mail, Bildschirmfoto, verlegter
Ausdruck), jemand, der es kennt, scheidet aus, oder es besteht ein Verdacht.

```
cd /opt/wochenangebot && sh deploy/sicherung-extern.sh passwort-neu
```

- Der Befehl erzeugt ein neues Passwort (wie `einrichten`), hinterlegt es im Repository, probiert es aus, ersetzt die
  Passwortdatei auf dem Server und entfernt erst danach **alle anderen** Schlüssel des Repositorys – den des bisherigen
  Passworts und auch solche, die jemand von Hand mit `restic key add` angelegt hat. Dann zeigt er das neue Passwort
  **einmal**. Stände, Timer und Karte bleiben, wie sie sind.
- **Danach sofort:** neues Passwort in den Passwortmanager (alten Eintrag ersetzen) und neu ausdrucken. Die Ausgabe
  nicht kopieren oder weitergeben.
- **Kopie prüfen, erst dann den alten Ausdruck vernichten** (*getestet*): `sh deploy/sicherung-extern.sh passwort-pruefen`
  liest das Passwort verdeckt ein (aus dem Passwortmanager einfügen bzw. vom Ausdruck abtippen) und vergleicht es mit der
  Passwortdatei auf dem Server. Erst bei „Stimmt“ ist die Kopie brauchbar – ein Tippfehler fiele sonst erst im Ernstfall
  auf, wenn der Server weg ist. Der Befehl ändert nichts und passt auch nach dem ersten Einrichten.
- Läuft gerade eine Übertragung, bricht der Befehl ab („läuft bereits – später erneut versuchen“) und ändert nichts.
- **Abbruch oder Fehler:** Die Passwortdatei auf dem Server öffnet das Repository zu jedem Zeitpunkt, die nächtliche
  Kopie läuft weiter. Solange kein Passwort angezeigt wurde, ist der Wechsel nicht abgeschlossen und das bisherige
  Passwort kann noch gelten – den Befehl einfach wiederholen. Das gilt auch, wenn die Verbindung zur Konsole genau
  während der Anzeige abriss: Dann gilt das bisherige schon nicht mehr, das neue wurde aber nicht gesehen.
- **Grenze – ältere Snapshots der Storage Box:** Der Wechsel verschlüsselt nichts neu. restic verschlüsselt die Daten
  mit einem Hauptschlüssel; das Passwort schließt nur die Schlüsseldatei auf, in der er liegt (Ordner `keys/`). Der
  Hauptschlüssel bleibt beim Wechsel derselbe. Ein Snapshot der Storage Box von vor dem Wechsel enthält noch die alte
  Schlüsseldatei: Wer das alte Passwort **und** Zugriff auf die Storage Box hat (Hetzner-Konto oder SSH-Schlüssel des
  Servers), öffnet damit weiter den Snapshot – und mit der alten Schlüsseldatei auch Stände von nach dem Wechsel
  (*getestet*). Das alte Passwort allein, ohne Zugriff auf die Storage Box, öffnet nichts. Die Lücke schließt sich,
  sobald die Snapshots von vor dem Wechsel gelöscht sind (*abgeleitet*): Automatische Snapshots ersetzt Hetzner der
  Reihe nach durch neuere, von Hand angelegte löscht Hetzner nie von selbst – diese in der Hetzner Console löschen
  (vorher einen neuen Snapshot anlegen: die Snapshots sind zugleich der Löschschutz, Abschnitt 2)
  ([Hetzner Docs, Storage Box Snapshots](https://docs.hetzner.com/storage/storage-box/snapshots/), gelesen am 17.11.2026).
- **Reicht nicht**, wenn auch der Zugriff auf die Storage Box in fremde Hände kam (Server übernommen, Hetzner-Konto):
  Dann braucht es ein neues Repository mit neuem Hauptschlüssel – ein eigener Schritt, den dieser Befehl nicht macht
  (restic-Dokumentation, [References, „Keys, Encryption and MAC“ und „Threat Model“](https://restic.readthedocs.io/en/stable/100_references.html),
  gelesen am 17.11.2026: das Passwort lässt sich wechseln, ohne die Daten neu zu verschlüsseln; den Hauptschlüssel
  wechselt nur `restic copy` in ein neues Repository).

### Grenzen

- **Die Karte ist ein Hinweis, kein Beleg.** Ihre Angaben stehen in `daten/sicherung-extern.php`. Der Ordner `daten/`
  ist in den Containern der Anwendung beschreibbar (nach der Datentrennung auch im Container der Kundenseite, wie bei
  `sicherung.php`). Wer dort Code als Benutzer der Anwendung ausführt, kann „aktuell“ fälschen. Verlässlich ist nur,
  was root auf dem Server sieht: `status` (liest ausschließlich das Repository, nie diese Datei) und `pruefen`.
- **Ein Stand kann einmal unvollständig sein** (*abgeleitet*): Startet während einer laufenden Übertragung eine
  Datensicherung (`sichern.sh` vor einem Release), kann der externe Stand dieses Laufs ein neues Archiv enthalten, aber
  den zugehörigen Stand der Dateiablage noch nicht. restic meldet das nicht, die Karte bleibt grün. Der nächste Lauf
  kopiert den fehlenden Teil; die älteren Stände sind nicht betroffen.
- **Statusdatei im Archiv der Datensicherung** (*abgeleitet*): Im Dateibetrieb packt `sichern.sh` auch
  `daten/sicherung-extern.php` ins Archiv (anders als `sicherung.php`). Würde die Datei genau dann ersetzt, während `tar`
  sie liest, bräche diese eine lokale Sicherung ab. Das Skript ersetzt die Datei deshalb nur, wenn die Sperre von
  `sichern.sh` frei ist, und wartet darauf bis zu 60 Sekunden (*getestet*). Läuft die Datensicherung länger, schreibt
  es den Status trotzdem – der Rest der Grenze; die nächste Datensicherung läuft wieder normal.
- **Eine vorgestellte Uhr** hinterlässt im Repository einen Stand mit einer Zeit in der Zukunft. Die Karte nennt immer
  die Zeit des letzten eigenen Laufs und warnt, wenn sie in der Zukunft liegt (*getestet*). `status` zeigt den
  neuesten Stand des Repositorys – ein Alter mit negativem Vorzeichen heißt: Uhr prüfen.

## 5. Fehlerbilder

| Anzeige | Bedeutung | Schritt |
| --- | --- | --- |
| „Übertragung fehlgeschlagen (restic Code …)“ | Storage Box nicht erreichbar, Schlüssel nicht (mehr) hinterlegt oder Platz voll | `sh deploy/sicherung-extern.sh jetzt` in der Konsole – die letzten Zeilen von restic nennen den Grund; Platz in der Hetzner Console prüfen |
| „Datensicherung läuft noch – externe Kopie ausgelassen“ | `sichern.sh` hielt die Sperre länger als 10 Minuten | nächste Nacht abwarten oder `jetzt` |
| „keine lokale Sicherung vorhanden“ | `sicherungen/` enthält kein Archiv | zuerst die Karte „Datensicherung“ klären |
| „kopiert, aber Aufräumen alter Stände fehlgeschlagen“ | Kopie ist da, alte Stände wurden nicht entfernt | meist vorübergehend; bleibt es, `pruefen` |
| „Prüfung des Repositorys fehlgeschlagen“ / „… weicht vom lokalen Original ab“ | Kopie beschädigt | nicht löschen; Snapshot der Storage Box sichern, dann klären |
| „Zeit unklar – … liegt in der Zukunft“ | Die Uhr des Servers ging beim letzten Lauf vor (oder geht jetzt nach) | `date` und `timedatectl` in der Konsole; nach der Korrektur `jetzt` – die Karte nennt dann wieder die richtige Zeit |
| ssh meldet „REMOTE HOST IDENTIFICATION HAS CHANGED“ | Schlüssel der Storage Box hat sich geändert | bei Hetzner nachfragen bzw. Statusmeldungen lesen; erst nach Klärung `.sicherung-extern-hosts` löschen, `einrichten` aufrufen und den neuen Fingerabdruck wie in Schritt 3.3 vergleichen |

## 6. Rücksicherung auf einem neuen Server (*abgeleitet, nicht getestet*; die restic-Befehle sind einzeln *getestet*)

Lage: Der alte Server ist weg. Gebraucht werden das **Repository-Passwort** (Passwortmanager bzw. Ausdruck) und der
Zugang zur Hetzner Console.

1. Neuen Server aufsetzen wie in `LIESMICH.md` (Docker, Repository nach `/opt/wochenangebot`, `.env`). Die Anwendung
   noch nicht starten.
2. `apt-get install -y restic`
3. Zugang zur Storage Box: **zuerst in der Hetzner Console das Passwort des Unterkontos neu setzen – immer.** Das alte
   wurde bei der Einrichtung nur einmal getippt und nirgends aufbewahrt (Schritt 3.4), und nach einer Übernahme des
   alten Servers wäre es ohnehin zu ersetzen. Dann einen **neuen** SSH-Schlüssel erzeugen und mit dem neuen Passwort
   hinterlegen (der alte Schlüssel lag nur auf dem alten Server):

   ```
   ssh-keygen -t ed25519 -N '' -f /root/.ssh/storagebox
   cat /root/.ssh/storagebox.pub | ssh -p 23 <Benutzer>@<Benutzer>.your-storagebox.de install-ssh-key
   ```

   ssh fragt hier „Are you sure you want to continue connecting?“: den Fingerabdruck wie in Schritt 3.3 mit der Liste
   von Hetzner vergleichen, erst dann `yes` und das neue Passwort. Wurde der alte Server übernommen, zusätzlich den
   alten Schlüssel entfernen (Datei `.ssh/authorized_keys` im Ordner des Unterkontos).

4. Stände ansehen (fragt nach dem Repository-Passwort):

   ```
   restic -o sftp.command="ssh -p 23 -i /root/.ssh/storagebox <Benutzer>@<Benutzer>.your-storagebox.de -s sftp" \
     -r sftp:<Benutzer>@<Benutzer>.your-storagebox.de:wochenangebot snapshots
   ```

   Hat ein Angreifer die Kopie gelöscht oder überschrieben: den Ordner aus einem **Snapshot** von vor dem Vorfall
   zurückkopieren (`/.zfs/snapshot/<Name>/`, nur lesbar), dann weiter. **Vorsicht beim Zurückspielen in der Hetzner
   Console:** Wer die Storage Box auf einen älteren Snapshot zurücksetzt, löscht alles, was danach entstand – auch
   **alle neueren Snapshots** (Hinweis der Hetzner-Oberfläche; so auch
   [Hetzner Docs, Storage Box Snapshots](https://docs.hetzner.com/storage/storage-box/snapshots/), gelesen am
   17.11.2026). Deshalb zuerst zurückkopieren und nur zurücksetzen, wenn feststeht, welcher Snapshot der richtige ist.
5. Den gewünschten Stand zurückholen (ohne Angabe: `latest`):

   ```
   restic -o sftp.command="…wie oben…" -r sftp:<Benutzer>@<Benutzer>.your-storagebox.de:wochenangebot restore latest --target /root/zurueck
   ```

   Danach liegt der Ordner unter `/root/zurueck/opt/wochenangebot/sicherungen/` – mit allen Archiven der letzten 30 Tage
   vor diesem Stand und den Ständen der Dateiablage (feste Verweise bleiben erhalten, *getestet*).
6. `mv /root/zurueck/opt/wochenangebot/sicherungen /opt/wochenangebot/sicherungen && chmod 700 /opt/wochenangebot/sicherungen`
7. Weiter wie bei jeder Wiederherstellung aus `sicherungen/`: `LIESMICH.md` (Abschnitt Datensicherung, „Wiederherstellen“),
   [`docs/datenbank.md`](../datenbank.md#sicherung-und-wiederherstellung) und für die Anmeldung
   [Rücksicherung der Anmeldung](inbetriebnahme-anmeldung.md#rücksicherung-der-anmeldung-keycloak). Nicht in der Sicherung:
   Schlüssel des Postfach-Passworts und `daten-anmeldung/vault/` (Postfach-Passwörter neu eingeben).
8. Externe Kopie auf dem neuen Server wieder einrichten: zuerst das Repository-Passwort aus dem Passwortmanager in
   seine Datei schreiben – mit `umask 077`, damit sie von Anfang an nur root lesen kann, und über `cat`, damit das
   Passwort nicht im Befehlsverlauf der Konsole landet:

   ```
   ( umask 077; cat > /opt/wochenangebot/.sicherung-extern-passwort )
   ```

   Passwort einfügen, Eingabetaste, dann Strg+D. Kontrolle: `ls -l /opt/wochenangebot/.sicherung-extern-passwort` zeigt
   `-rw-------`. Dann Abschnitt 3 ab Schritt 3.1. Das Skript findet das vorhandene Repository („Repository vorhanden“)
   und setzt die Reihe der Stände fort.

**Einmal üben** (Empfehlung, bevor es ernst wird): Schritte 2 bis 5 auf einem beliebigen Linux-Rechner außerhalb des
Servers durchspielen, nur mit Passwortmanager und Hetzner-Zugang. Erst dann ist bewiesen, dass die Unterlagen reichen.

## 7. Rückfall

- Die externe Kopie ist vom Rest entkoppelt: `sh deploy/sicherung-extern.sh aus` stellt den Zustand vor der
  Inbetriebnahme her. An `sichern.sh`, an den Daten und an den lokalen Sicherungen ändert sie nichts.
- Rückfall auf ein Release vor dieser Änderung: vorher `aus` ausführen (das ältere Release enthält das Skript nicht, der
  Timer liefe ins Leere). Die Statusdatei `daten/sicherung-extern.php` kennt das ältere Release nicht; sie kann gelöscht
  werden.
- **Vor einem Umschalten der Speicherart unter einem älteren Release** (Dateien → SQLite, `datenbank-umschalten.sh`)
  **muss** `daten/sicherung-extern.php` gelöscht werden (*getestet* mit `deploy/datenbank.py` beider Stände): Das ältere
  `datenbank.py` hält die Datei für ein gewöhnliches Dokument und nimmt sie in die Datenbank auf. Nach dem Vorrollen
  lehnt das neue `datenbank.py` die Datenbank dann ab („Invalid database key“), und damit scheitert auch jede
  Datensicherung (`sichern.sh`). Ist es schon passiert (*abgeleitet*): unter dem älteren Release zurück auf Dateien
  schalten, die Datei löschen, erneut umschalten. Ohne Umschalten der Speicherart ist der Rückfall unkritisch.

## 8. Offene Entscheidungen für den Inhaber

- **Löschfristen:** Mit 12 Monatsständen leben gelöschte Daten (z. B. ausgeschiedene Mitarbeiter, gelöschte Kunden) in
  der externen Kopie bis zu rund 13 Monate weiter, lokal nur 30 Tage. Das ist für eine Sicherung üblich, gehört aber
  ins Löschkonzept. Kürzer geht mit drei Zahlen am Kopf des Skripts (`TAGE`, `WOCHEN`, `MONATE`).
- **Regelmäßige Prüfung:** `pruefen` läuft nur von Hand. Ein zweiter Timer (z. B. wöchentlich) wäre ein kleiner Nachtrag.
- **Zweite Aufbewahrung des Passworts:** Wer außer dem Inhaber kommt im Ernstfall an Passwortmanager bzw. Ausdruck?
