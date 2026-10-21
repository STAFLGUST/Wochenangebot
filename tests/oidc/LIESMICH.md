# Anmeldung über Keycloak – Testumgebung (Roadmap 7b)

Bildet die geplante Mitarbeiteranmeldung aus ADR-003 vollständig nach – **nur in der CI und lokal**, nie auf dem Server
(GR-111). Nichts hiervon ändert `angebot-stafl.de`: ohne `WA_OIDC=1` im Webserver verhält sich die Anwendung wie bisher.

```text
Browser ──TLS──▶ Caddy (Test-CA) ─┬─ login.stafl.test      ─▶ Keycloak 26.7.5 (Realm „mitarbeiter“) ─▶ PostgreSQL (nur Keycloak)
                                  ├─ dashboard.stafl.test  ─▶ Apache + mod_auth_openidc (Client „dashboard“) ─▶ app/ + dashboard/
                                  └─ angebot.stafl.test    ─▶ Apache + mod_auth_openidc (Client „angebot“)   ─▶ app/
```

| Datei | Inhalt |
| --- | --- |
| `umgebung.sh` | `start` / `stop`: PostgreSQL, Keycloak, Caddy, Apache; Versionen mit Prüfsumme, Geheimnisse bei jedem Start neu (`tests/.arbeit/oidc/geheim.env`) |
| `realm-mitarbeiter.json` | Test-Realm: Brute-Force-Schutz, nur HTTPS, keine Selbstregistrierung, Pflicht zum zweiten Faktor, Sitzung 30 Min. Leerlauf / 10 Std.; Clients vertraulich, nur Code-Ablauf mit PKCE (S256), exakte Rücksprungadressen, kein CORS, Back-Channel-Logout. Testnutzer mit Testkennwörtern (keine echten Daten) |
| `Caddyfile` | TLS wie in der Produktion; auf `login.` nur `/realms/mitarbeiter/` und `/resources/` (Verwaltung und Master-Realm nie öffentlich) |
| `apache.conf` | je Host ein eigener Client und eine eigene Sitzung (`__Host-oidc_sitzung`), Schnittstelle ohne Anmeldung 401, Identität nur als Server-Umgebung (`OIDCPassClaimsAs environment`) |
| `test_oidc.py` | 65 Prüfungen (Härtung, zweiter Faktor, Sitzung je Host, Single Sign-on, Rechte, gesperrte/unbekannte Konten, Abmelden für alle Anwendungen) |

Lokal (Ubuntu 24.04 mit `apache2 libapache2-mod-auth-openidc libapache2-mod-php8.3 postgresql`, Java 21):

```sh
bash tests/oidc/umgebung.sh start && python3 tests/oidc/test_oidc.py; bash tests/oidc/umgebung.sh stop
```

Die Hosts `*.stafl.test` trägt das Skript in `/etc/hosts` ein (mit `sudo`, wenn nicht als root). Ports: 8443 (fest, steht
in den Rücksprungadressen des Realms), 8081, 8180/9180 (Keycloak), 8280 (Apache), 5433 (PostgreSQL).

Was die Anwendung dazu beiträgt, steht in `app/api/lib/oidc.php`: Konto zur Keycloak-Kennung (Feld `oidcSub`,
erste Anmeldung über den gleichen Benutzernamen), Rechte und „aktiv“ weiterhin aus dem eigenen Nutzerkonto, eigene
Anmeldeverfahren gesperrt (Registerfeld `lokale_anmeldung`), Abmelden über Keycloak.

Noch offen (Roadmap 7b-2): erneute Anmeldung für sensible Aktionen (`max_age=0`) – bis dahin werden Aktionen mit
Passwortbestätigung auf Keycloak-Hosts abgewiesen; serverseitige Prüfung der Anmeldestärke (`acr`/`amr`); Passkeys im Realm;
eigenes Container-Image mit mod_auth_openidc für den späteren Betrieb.
