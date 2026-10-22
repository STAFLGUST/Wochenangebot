# Anmeldung über Keycloak – Testumgebung (Roadmap 7b)

Bildet die geplante Mitarbeiteranmeldung aus ADR-003 vollständig nach – **nur in der CI und lokal**, nie auf dem Server
(GR-111). Nichts hiervon ändert `angebot-stafl.de`: ohne `WA_OIDC=1` im Webserver verhält sich die Anwendung wie bisher.

```text
Browser ──TLS──▶ Caddy (Test-CA) ─┬─ login.stafl.test      ─▶ Keycloak 26.8.1 (Realm „mitarbeiter“) ─▶ PostgreSQL (nur Keycloak)
                                  ├─ dashboard.stafl.test  ─▶ Apache + mod_auth_openidc (Client „dashboard“) ─▶ app/ + dashboard/
                                  └─ angebot.stafl.test    ─▶ Apache + mod_auth_openidc (Client „angebot“)   ─▶ app/
```

| Datei | Inhalt |
| --- | --- |
| `umgebung.sh` | `start` / `stop`: PostgreSQL (UTF-8, nur für Keycloak), Keycloak (veraltete Funktionen abgeschaltet), Caddy, Apache; Versionen mit Prüfsumme, Geheimnisse bei jedem Start neu (`tests/.arbeit/oidc/geheim.env`). Keycloak-Updates: Version und SHA-256 hier eintragen, CI-Auftrag muss grün sein (ADR-003) |
| `realm-mitarbeiter.json` | Test-Realm: Brute-Force-Schutz, nur HTTPS, keine Selbstregistrierung, Pflicht zum zweiten Faktor, Sitzung 30 Min. Leerlauf / 10 Std.; Clients vertraulich, nur Code-Ablauf mit PKCE (S256), exakte Rücksprungadressen, kein CORS, Back-Channel-Logout. Testnutzer mit Testkennwörtern (keine echten Daten) |
| `Caddyfile` | TLS wie in der Produktion; auf `login.` nur `/realms/mitarbeiter/` und `/resources/` (Verwaltung und Master-Realm nie öffentlich) |
| `apache.conf` | je Host ein eigener Client und eine eigene Sitzung (`__Host-oidc_sitzung`), Schnittstelle ohne Anmeldung 401, Identität nur als Server-Umgebung (`OIDCPassClaimsAs environment`) |
| `test_oidc.py` | 112 Prüfungen (Härtung, zweiter Faktor mit Einmalcode oder Passkey und Anmeldestärke, erneute Anmeldung, Sitzung je Host, Single Sign-on, Rechte, gesperrte/unbekannte Konten, Abmelden für alle Anwendungen, Konten über die Serverkonsole mit `deploy/anmeldung/konten.sh`) |

Lokal (Ubuntu 24.04 mit `apache2 libapache2-mod-auth-openidc libapache2-mod-php8.3 postgresql`, Java 21):

```sh
bash tests/oidc/umgebung.sh start && python3 tests/oidc/test_oidc.py; bash tests/oidc/umgebung.sh stop
```

Die Hosts `*.stafl.test` trägt das Skript in `/etc/hosts` ein (mit `sudo`, wenn nicht als root). Ports: 8443 (fest, steht
in den Rücksprungadressen des Realms), 8081, 8180/9180 (Keycloak), 8280 (Apache), 5433 (PostgreSQL).

Was die Anwendung dazu beiträgt, steht in `app/api/lib/oidc.php`: Konto zur Keycloak-Kennung (Feld `oidcSub`,
erste Anmeldung über den gleichen Benutzernamen), Rechte und „aktiv“ weiterhin aus dem eigenen Nutzerkonto, eigene
Anmeldeverfahren gesperrt (Registerfeld `lokale_anmeldung`), Abmelden über Keycloak.

**Anmeldestärke:** Der Realm meldet über `acr`, wie angemeldet wurde (`pwd` = nur Passwort, `mfa` = mit zweitem Faktor;
eigener Ablauf `mitarbeiter-browser` mit Stufen). Die Clients verlangen `mfa`, und unser Server prüft es zusätzlich
(`WA_OIDC_ACR`, Standard `mfa`) – auch ein falsch eingestellter Client öffnet keinen Zugang ohne zweiten Faktor.

**Sensible Aktionen** (sonst Passwortbestätigung): bestätigt ist, wer sich innerhalb der eingestellten Bestätigungsdauer
bei Keycloak angemeldet hat. Danach antwortet der Server mit `reauth_required` und einer Adresse; der Eingabebereich
leitet zur erneuten Anmeldung (`max_age=0`: Passwort und zweiter Faktor) und kehrt auf dieselbe Seite zurück. Ziele nur
auf dem eigenen Host (`OIDCRedirectURLsAllowed`, keine offene Weiterleitung).

**Passkeys:** zweiter Faktor ist ein Passkey, wenn der Nutzer einen eingerichtet hat, sonst der Einmalcode – wer keinen
zweiten Faktor hat, muss den Einmalcode bei der ersten Anmeldung einrichten (Ablauf `mitarbeiter-zweiter-faktor`:
„Condition – user configured“ und „Condition – credential“). Richtlinie: ES256/RS256, Bestätigung am Gerät (PIN oder
Biometrie) Pflicht, kein Gerät doppelt. Einrichten über die Pflichtaktion „Passkey registrieren“ (vom Administrator
gesetzt) oder die Kontoseite von Keycloak. Getestet mit einem virtuellen Authenticator in Chromium.

Noch offen: Anmeldung ganz ohne Passwort (nur Passkey); eigenes Container-Image mit mod_auth_openidc für den späteren Betrieb.
