# SQLite-Datenablage (Schema 1)

Dieser Release unterstützt SQLite zusätzlich zur bisherigen Dateiablage. Ein Merge oder Release
aktiviert die Datenbank **nicht**. Die Verantwortlichen führen die Migration anschließend bewusst
im Wartungsfenster durch. Externe Sicherungen sind nicht Bestandteil dieser Änderung.

## Struktur und Grenzen

`daten/.sqlite/store.sqlite` enthält die Tabelle `documents`: Primärschlüssel `name`, JSON-Nutzdaten
`payload`, Änderungszeit `mtime`. Angebote, Kunden, Nutzer, Bestellwünsche, Merklisten, Sitzungen,
Sicherheitsregeln, Protokolle, Historie und Versionen werden vollständig übernommen. Die erste
Migration behält die geprüften Geschäfts-Datenformate bei. Sie ist noch keine Normalisierung in
separate SQL-Zeilen je Kunde/Artikel; große Listen werden weiterhin als JSON-Dokument gelesen.

Die vorhandenen `with_lock`-Bereiche verwenden SQLite-Schreibtransaktionen (`BEGIN IMMEDIATE`),
auch über mehrere Dokumente und verschachtelte Sperren. Veröffentlichung und Entwurfsänderung
inklusive Revisionsprüfung haben zusätzliche gemeinsame Transaktionen. Unerwartete Ausnahmen
rollen diese zurück. Beabsichtigte API-Fehler dürfen vorher erfasste Fehlversuche behalten.
SQLite verwendet das normale Rollback-Journal mit `synchronous=FULL`, keine Netzwerkfreigabe.
Gleichzeitige Schreiber werden serialisiert (10 Sekunden Wartezeit, danach Fehler statt Datenverlust).
E-Mails selbst sind externe Wirkungen und keine zurückrollbaren Datenbanktransaktionen.

Außerhalb der Datenbank bleiben der **Postfach-Verschlüsselungsschlüssel**, die Statusdateien von
Sicherung/Deployment und die binäre Geo-Datenbank. Der Schlüssel bleibt wie bisher aus Sicherungen
ausgeschlossen; nach Wiederherstellung auf einem neuen Server das Postfachpasswort neu eingeben.

`.sqlite-active` wählt SQLite. Fehlt bei aktivem Marker die Datenbank oder stimmt ihr Schema nicht,
bricht die Anwendung ab – sie liest **nicht** stillschweigend veraltete PHP-Dateien. Diese bleiben
nach der Migration zunächst erhalten, werden aber nicht weitergeschrieben. Niemals nur den Marker
löschen oder alte Dateien über die Datenbank kopieren.

## Kontrollierte Aktivierung durch den Betreiber

1. PR prüfen, grüne CI auf main abwarten und den vorhandenen kontrollierten Release auslösen.
2. Snapshot erstellen; kurzes Wartungsfenster ankündigen. Serverzugang offen halten.
3. Im Projektordner: `sh deploy/datenbank-umschalten.sh migrate`.
   Das Skript erstellt zuerst die bestehende lokale Sicherung, prüft PDO_SQLITE im tatsächlichen
   PHP-Container, stoppt die Anwendung, übernimmt und vergleicht alle Dokumente und startet danach
   wieder. Beschädigte Quelldaten oder eine bereits vorhandene Datenbank brechen die Übernahme ab.
   Nach einem Fehler bleibt die Anwendung bewusst gestoppt: Ursache prüfen, nicht blind erneut starten.
   Vorher prüft das Skript ohne Sicherung und ohne Stopp: Ist SQLite schon aktiv (`daten/.sqlite-active`), meldet es
   „bereits aktiv – nichts zu tun“; liegt nur ein alter Ordner `daten/.sqlite` ohne Marker vor, bricht es ab, ohne die
   Anwendung anzuhalten. Ebenso tut `rollback` nichts, wenn SQLite nicht aktiv ist (Test: `tests/deploy/test_datenbank_umschalten.sh`).
4. Anmeldung, Kundenangebot, Merkliste, Entwurf/Veröffentlichung und Bestellwunsch prüfen.
5. `sh deploy/sichern.sh --jetzt`: Neue Sicherung mit SQLite erzeugen und Status kontrollieren.

Die Werkzeuge verändern keine Daten auf einem entfernten Server und starten keinen Release.
Notfallwerkzeuge (`passwort-zuruecksetzen.sh`, `ip-freigabe-aus.sh`) laufen im Container als `www-data`,
damit weder Datenbank-Journal noch Sperrdateien root gehören. Eine dennoch von root angelegte Sperrdatei
blockiert die Anwendung nicht (Sperre wird dann lesend gesetzt).
`python3 deploy/datenbank.py check daten` prüft Integrität und Schema. Die internen Befehle `migrate`
und `rollback` verlangen `--offline`; nur verwenden, wenn die Anwendung tatsächlich gestoppt ist.

## Sicherung und Wiederherstellung

Der bestehende Timer verwendet bei aktivem SQLite die SQLite-Backup-API über Python. Das Archiv
enthält einen konsistenten Snapshot, keinen unkoordinierten Dateiabzug einer geöffneten Datenbank.
Die Probeentpackung prüft Integrität, Schema und sämtliche JSON-Dokumente. Python 3 ist für diese
Sicherungen erforderlich. Die CI testet Sicherung, Korruptionserkennung und Öffnen des Snapshots.

Zur Wiederherstellung: Anwendung stoppen, aktuellen Datenordner separat sichern, Archiv in einen
leeren Datenordner entpacken, Eigentümer wieder auf Containerbenutzer 33:33 setzen (Datenbankordner
700, Datenbank 600), `python3 deploy/datenbank.py check daten`, dann App starten und Funktionen
prüfen. Keine Sicherungen verschiedener Zeitpunkte mischen. Das Postfachpasswort nötigenfalls neu
hinterlegen. Ein vollständiger Wiederherstellungstest am Produktionssystem steht weiterhin aus.

## Rückfall ohne Verlust neuer Daten

Vor Rückkehr zu einem älteren Release ohne SQLite-Unterstützung:
`sh deploy/datenbank-umschalten.sh rollback`. Das stoppt die Anwendung nach einer Sicherung,
exportiert **den aktuellen Datenbankstand**, entfernt inzwischen gelöschte Altdokumente und
schaltet erst nach erfolgreichem Vergleich auf Dateien zurück. Erst anschließend den bisherigen
Release-Rückfall durchführen. Die Release-Skripte verhindern den direkten Rückfall auf Code ohne
Speicherschicht, solange SQLite aktiv ist. Nicht über ein manuelles `git reset` umgehen.
Die inaktive Datenbank bleibt zur Untersuchung erhalten; vor einer späteren erneuten Migration
muss `.sqlite` im gestoppten Zustand separat archiviert/umbenannt werden.

## Webschutz und Tests

Caddy verweigert `/data` und dessen Unterpfade. Der Datenbankordner enthält zusätzlich eine
Apache-Zugriffssperre, einschließlich Journaldateien. Ein CI-Test prüft das echte PHP-Apache-Image.
Beide Speicherarten durchlaufen die vollständigen E2E-Tests. Zusätzliche Tests prüfen parallele
Schreiber, Transaktionsabbruch, Importvergleich, fehlende Datenbank, konsistente Snapshots,
Rückkonvertierung inklusive Löschungen und den Ausschluss des Postfachschlüssels.

Grundlagen: https://www.php.net/manual/en/ref.pdo-sqlite.php und https://www.sqlite.org/backup.html
