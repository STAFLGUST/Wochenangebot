#!/usr/bin/env bash
# Prüft die vorbereitete Betriebskonfiguration der zentralen Anmeldung (deploy/anmeldung) – lokal mit Docker und in der CI.
# Startet nichts auf einem Server. Prüft:
#   1. Realm für den Betrieb aktuell (aus dem geprüften Test-Realm erzeugt, ohne Testnutzer, Geheimnisse nur Platzhalter)
#   2. docker compose mit Ergänzungsdatei gültig; alle neuen Images fest über Digest; Kundenseite in eigenem Container
#      (ADR-007): app ohne Anmelde-Geheimnisse und Keycloak-Netz, gehärtet; app-mitarbeiter vollständig
#   3. Anwendungs-Image mit apache-oidc.conf: Konfiguration gültig; angebot-stafl.de (Standard-Host) verhält sich
#      unverändert; die neuen Hosts liefern ohne Anmeldung nichts aus der Anwendung aus
#   3a. Beide Anwendungs-Container und der Dienst postausgang starten wie im Betrieb (Compose) und sind voneinander getrennt
#   3b. Keycloak startet wirklich – mit Start-Konto und nach der Einrichtung ohne (Neustart)
#   4. Caddyfile (mit den Anmelde-Hosts) gültig; deren Ziele gibt es nur mit der Ergänzungsdatei
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HIER="$REPO/deploy/anmeldung"
FEHLER=0
ok() { echo "PASS $1"; }
nein() { echo "FAIL $1${2:+  $2}"; FEHLER=1; }

python3 "$REPO/werkzeuge/realm_produktion.py" --pruefen >/dev/null && ok "Realm für den Betrieb aktuell" || nein "Realm veraltet (werkzeuge/realm_produktion.py)"
python3 - "$HIER/realm-mitarbeiter.json" <<'PY' && ok "Realm: keine Testnutzer, keine Testadressen, Geheimnisse nur Platzhalter" || nein "Realm enthält Testdaten oder Geheimnisse"
import json, sys
t = open(sys.argv[1], encoding='utf-8').read(); r = json.loads(t)
assert 'users' not in r and 'stafl.test' not in t and 'nur-fuer-tests' not in t
assert all(c['secret'].startswith('@GEHEIM_') for c in r['clients'])
host = {'dashboard': 'dashboard-stafl.de', 'angebot': 'angebot.dashboard-stafl.de', 'verwaltung': 'verwaltung.dashboard-stafl.de',
        'bestand': 'bestand.dashboard-stafl.de', 'hr': 'hr.dashboard-stafl.de',
        'crm': 'crm.dashboard-stafl.de', 'marketing': 'marketing.dashboard-stafl.de', 'sicherheit': 'sicherheit.dashboard-stafl.de',
        'controlling': 'controlling.dashboard-stafl.de', 'leergut': 'leergut.dashboard-stafl.de',
        'rewe': 'rewe.dashboard-stafl.de', 'qs': 'qs.dashboard-stafl.de'}
# Hosts mit Anmeldung; dazu genau ein Client ohne Host: „konten“ (Mitarbeiterkonten aus der Verwaltung, nur Service-Account)
konten = [c for c in r['clients'] if c['clientId'] == 'konten']
assert len(konten) == 1 and konten[0]['serviceAccountsEnabled'] is True and konten[0]['standardFlowEnabled'] is False \
    and konten[0]['directAccessGrantsEnabled'] is False and not konten[0].get('redirectUris')
assert sorted(c['clientId'] for c in r['clients'] if c['clientId'] != 'konten') == sorted(host)
assert all(c['redirectUris'] == [f"https://{host[c['clientId']]}/oidc/callback"] for c in r['clients'] if c['clientId'] != 'konten')
assert all(c['secret'] == f"@GEHEIM_{c['clientId'].upper()}@" for c in r['clients'])
PY

# ── 2. Compose ──
ENV="$(mktemp)"; trap 'rm -f "$ENV"; docker rm -f stafl-pruefung >/dev/null 2>&1 || true' EXIT
cat > "$ENV" <<'EOF'
DOMAIN=angebot-stafl.de
OIDC_SECRET_DASHBOARD=pruefung
OIDC_SECRET_ANGEBOT=pruefung
OIDC_CRYPTO_DASHBOARD=pruefung-a
OIDC_CRYPTO_ANGEBOT=pruefung-b
KC_DB_PASSWORD=pruefung
EOF
if docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config -q 2>/tmp/compose-fehler.txt; then ok "docker compose mit Ergänzungsdatei gültig"; else nein "docker compose" "$(cat /tmp/compose-fehler.txt)"; fi
ohne="$(grep -E '^\s+image:' "$HIER/docker-compose.anmeldung.yml" | grep -v '@sha256:' | grep -v 'stafl-app:' || true)"
[ -z "$ohne" ] && ok "neue Images fest über Digest" || nein "Images ohne Digest" "$ohne"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); kc=d['services']['keycloak']; db=d['services']['keycloak-db']; \
assert all(p.get('host_ip')=='127.0.0.1' for p in kc.get('ports',[])); assert not db.get('ports'); assert list(db['networks'])==['anmeldung']; \
assert d['networks']['anmeldung'].get('internal') is True" \
  && ok "Keycloak nur lokal erreichbar, Datenbank nur im internen Netz" || nein "Netz/Ports von Keycloak bzw. Datenbank"
# Ziele der Anmelde-Hosts in Caddy (app-mitarbeiter, keycloak) nur mit der Ergänzungsdatei – ohne sie: 502 statt App ohne Anmeldung
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'app-mitarbeiter' in d['services'] and 'app-mitarbeiter' not in json.dumps(d['services']['app'])" \
  && docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); s=d['services']; assert 'keycloak' not in s; assert all('app-mitarbeiter' not in json.dumps(v) for v in s.values())" \
  && ok "Ziele app-mitarbeiter und keycloak nur mit der Ergänzungsdatei" || nein "Netzwerkname app-mitarbeiter bzw. keycloak"
# Release vor dem Konsolenschritt für die Verwaltung (Werte fehlen in .env): Anwendung startet trotzdem, Schlüssel nie leer
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_VERWALTUNG']=='pruefung-b' and e['OIDC_SECRET_VERWALTUNG']" \
  && ok "Verwaltung: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "Verwaltung ohne Werte in .env"
printf 'OIDC_SECRET_VERWALTUNG=pruefung-v\nOIDC_CRYPTO_VERWALTUNG=pruefung-c\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_VERWALTUNG']=='pruefung-c' and e['OIDC_SECRET_VERWALTUNG']=='pruefung-v'" \
  && ok "Verwaltung: eigene Werte aus .env" || nein "Verwaltung: eigene Werte aus .env"
# Bestand (Stand 4) genauso: vor dem Konsolenschritt startbar, danach eigene Werte
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_BESTAND']=='pruefung-b' and e['OIDC_SECRET_BESTAND']" \
  && ok "Bestand: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "Bestand ohne Werte in .env"
printf 'OIDC_SECRET_BESTAND=pruefung-s\nOIDC_CRYPTO_BESTAND=pruefung-d\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_BESTAND']=='pruefung-d' and e['OIDC_SECRET_BESTAND']=='pruefung-s'" \
  && ok "Bestand: eigene Werte aus .env" || nein "Bestand: eigene Werte aus .env"
# HR (Stand 5) genauso: vor dem Konsolenschritt startbar, danach eigene Werte
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_HR']=='pruefung-b' and e['OIDC_SECRET_HR']" \
  && ok "HR: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "HR ohne Werte in .env"
printf 'OIDC_SECRET_HR=pruefung-h\nOIDC_CRYPTO_HR=pruefung-e\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_HR']=='pruefung-e' and e['OIDC_SECRET_HR']=='pruefung-h'" \
  && ok "HR: eigene Werte aus .env" || nein "HR: eigene Werte aus .env"
# CRM (Stand 6) genauso: vor dem Konsolenschritt startbar, danach eigene Werte
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_CRM']=='pruefung-b' and e['OIDC_SECRET_CRM']" \
  && ok "CRM: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "CRM ohne Werte in .env"
printf 'OIDC_SECRET_CRM=pruefung-k\nOIDC_CRYPTO_CRM=pruefung-f\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_CRM']=='pruefung-f' and e['OIDC_SECRET_CRM']=='pruefung-k'" \
  && ok "CRM: eigene Werte aus .env" || nein "CRM: eigene Werte aus .env"
# Marketing (Stand 7) genauso
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_MARKETING']=='pruefung-b' and e['OIDC_SECRET_MARKETING']" \
  && ok "Marketing: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "Marketing ohne Werte in .env"
printf 'OIDC_SECRET_MARKETING=pruefung-m\nOIDC_CRYPTO_MARKETING=pruefung-g\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_MARKETING']=='pruefung-g' and e['OIDC_SECRET_MARKETING']=='pruefung-m'" \
  && ok "Marketing: eigene Werte aus .env" || nein "Marketing: eigene Werte aus .env"
# Sicherheit (Stand 9) genauso
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_SICHERHEIT']=='pruefung-b' and e['OIDC_SECRET_SICHERHEIT']" \
  && ok "Sicherheit: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "Sicherheit ohne Werte in .env"
printf 'OIDC_SECRET_SICHERHEIT=pruefung-s\nOIDC_CRYPTO_SICHERHEIT=pruefung-t\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_SICHERHEIT']=='pruefung-t' and e['OIDC_SECRET_SICHERHEIT']=='pruefung-s'" \
  && ok "Sicherheit: eigene Werte aus .env" || nein "Sicherheit: eigene Werte aus .env"
# Controlling (Stand 10) genauso
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_CONTROLLING']=='pruefung-b' and e['OIDC_SECRET_CONTROLLING']" \
  && ok "Controlling: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "Controlling ohne Werte in .env"
printf 'OIDC_SECRET_CONTROLLING=pruefung-u\nOIDC_CRYPTO_CONTROLLING=pruefung-v\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_CONTROLLING']=='pruefung-v' and e['OIDC_SECRET_CONTROLLING']=='pruefung-u'" \
  && ok "Controlling: eigene Werte aus .env" || nein "Controlling: eigene Werte aus .env"
# Leergut (Stand 11) genauso
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_LEERGUT']=='pruefung-b' and e['OIDC_SECRET_LEERGUT']" \
  && ok "Leergut: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "Leergut ohne Werte in .env"
printf 'OIDC_SECRET_LEERGUT=pruefung-w\nOIDC_CRYPTO_LEERGUT=pruefung-x\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_LEERGUT']=='pruefung-x' and e['OIDC_SECRET_LEERGUT']=='pruefung-w'" \
  && ok "Leergut: eigene Werte aus .env" || nein "Leergut: eigene Werte aus .env"
# REWE (Stand 12) genauso
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_REWE']=='pruefung-b' and e['OIDC_SECRET_REWE']" \
  && ok "REWE: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "REWE ohne Werte in .env"
printf 'OIDC_SECRET_REWE=pruefung-y\nOIDC_CRYPTO_REWE=pruefung-z\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_REWE']=='pruefung-z' and e['OIDC_SECRET_REWE']=='pruefung-y'" \
  && ok "REWE: eigene Werte aus .env" || nein "REWE: eigene Werte aus .env"
# Qualitätssicherung (Stand 13) genauso
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_QS']=='pruefung-b' and e['OIDC_SECRET_QS']" \
  && ok "QS: ohne eigene Werte in .env startbar (Schlüssel des Eingabebereichs)" || nein "QS ohne Werte in .env"
printf 'OIDC_SECRET_QS=pruefung-q1\nOIDC_CRYPTO_QS=pruefung-q2\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; e=json.load(sys.stdin)['services']['app-mitarbeiter']['environment']; assert e['OIDC_CRYPTO_QS']=='pruefung-q2' and e['OIDC_SECRET_QS']=='pruefung-q1'" \
  && ok "QS: eigene Werte aus .env" || nein "QS: eigene Werte aus .env"

# Alter Eingabebereich: im Betrieb stillgelegt; Notzugang nur über einen SSH-Tunnel zu app-mitarbeiter (ADR-007 Regel 6,
# deploy/notzugang.sh): eigener Port nur auf 127.0.0.1, offen nur mit WA_NOTZUGANG=an – die Kundenseite öffnet ihn nie
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; s=json.load(sys.stdin)['services']; assert all(s[n]['environment']['WA_EIGENE_ANMELDUNG']=='aus' for n in ('app', 'app-mitarbeiter')); \
assert s['app-mitarbeiter']['environment']['WA_NOTZUGANG']=='aus' and 'WA_NOTZUGANG' not in s['app']['environment']" \
  && ok "alter Eingabebereich: im Betrieb stillgelegt (beide Anwendungs-Container), Notzugang geschlossen" || nein "alter Eingabebereich nicht stillgelegt"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; s=json.load(sys.stdin)['services']; p=s['app-mitarbeiter'].get('ports',[]); \
assert len(p)==1 and p[0].get('host_ip')=='127.0.0.1' and str(p[0].get('published'))=='8190' and int(p[0].get('target'))==8090; assert not s['app'].get('ports')" \
  && ok "Notzugang: nur 127.0.0.1:8190 → app-mitarbeiter:8090 (SSH-Tunnel), Kundenseite ohne eigenen Port" || nein "Port des Notzugangs"
printf 'WA_EIGENE_ANMELDUNG=an\nWA_NOTZUGANG=an\nNOTZUGANG_PORT=8191\n' >> "$ENV"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json 2>/dev/null \
  | python3 -c "import sys,json; s=json.load(sys.stdin)['services']; assert s['app']['environment']['WA_EIGENE_ANMELDUNG']=='aus'; \
assert s['app-mitarbeiter']['environment']['WA_EIGENE_ANMELDUNG']=='aus' and s['app-mitarbeiter']['environment']['WA_NOTZUGANG']=='an'; \
assert str(s['app-mitarbeiter']['ports'][0]['published'])=='8191' and s['app-mitarbeiter']['ports'][0]['host_ip']=='127.0.0.1'" \
  && ok "Notzugang: über .env einschaltbar nur für app-mitarbeiter; frühere Zeile WA_EIGENE_ANMELDUNG=an öffnet die Kundenseite nicht mehr" || nein "Notzugang über .env"
sed -i -e '/^WA_EIGENE_ANMELDUNG=/d' -e '/^WA_NOTZUGANG=/d' -e '/^NOTZUGANG_PORT=/d' "$ENV"

# Kundenseite in eigenem Container (ADR-007): app ohne Anmelde-Geheimnisse, Dashboard und Keycloak-Netz, gehärtet;
# app-mitarbeiter mit allem, was app aus docker-compose.yml bekommt (kein Auseinanderlaufen), plus Anmeldung
MIT="$(mktemp)"; OHNE="$(mktemp)"
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" -f "$HIER/docker-compose.anmeldung.yml" config --format json > "$MIT" 2>/dev/null
docker compose --env-file "$ENV" -f "$REPO/docker-compose.yml" config --format json > "$OHNE" 2>/dev/null
pruefe_json() { python3 - "$MIT" "$OHNE" "$1" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); basis = json.load(open(sys.argv[2]))['services']['app']; s = d['services']
app, ma, was = s['app'], s['app-mitarbeiter'], sys.argv[3]
ziele = lambda x: {v['target'] for v in x.get('volumes', [])}
if was == 'kunden-geheimnisse':
    assert not [k for k in app['environment'] if k.startswith('OIDC_') or k.startswith('WA_KONTEN')], app['environment'].keys()
elif was == 'kunden-dateien':
    assert ziele(app) == {'/var/www/html', '/var/www/html/data'}, ziele(app)
elif was == 'kunden-netz':
    assert set(app['networks']) == {'default'} and set(ma['networks']) == {'intern'}
    assert set(s['keycloak']['networks']) == {'intern', 'anmeldung'} and {'default', 'edge', 'intern'} <= set(s['caddy']['networks'])
    assert d['networks']['intern'].get('internal') is not True   # Ausgang (Postfach, Keycloak-Metadaten) bleibt möglich
elif was == 'kunden-haertung':
    assert app.get('read_only') is True and 'no-new-privileges:true' in app.get('security_opt', [])
    assert {t.split(':')[0] for t in app.get('tmpfs', [])} == {'/tmp', '/run'}
    assert float(app['cpus']) > 0 and int(app['mem_limit']) > 0 and int(app['pids_limit']) > 0
elif was == 'mitarbeiter-vollstaendig':
    assert ma['image'] == app['image'] and ma.get('pull_policy') == 'never' and app.get('build') and not ma.get('build')
    fehlt = {k: v for k, v in basis['environment'].items() if ma['environment'].get(k) != v}
    assert not fehlt, fehlt
    assert {'/var/www/html', '/var/www/html/data', '/var/www/dashboard', '/etc/apache2/sites-enabled/zz-stafl-oidc.conf', '/var/www/karte'} <= ziele(ma)
    assert ma['environment']['OIDC_SECRET_KONTEN'] and ma['environment']['WA_KONTEN_URL'] == 'http://keycloak:8080'
    assert ma.get('restart') == 'unless-stopped' and ma['logging']['options']['max-size'] == '10m'
elif was == 'postausgang-kunde':
    # Postausgang von innen (ADR-007): Kundenseite legt E-Mails nur ab, kennt kein Postfach und keinen Schlüssel
    e = app['environment']
    assert e['WA_POSTAUSGANG'] == 'warteschlange' and 'WA_GEHEIM_DIR' not in e, e
    assert {k for k in basis['environment'] if k.startswith('MAIL_')} <= set(e) and all(e[k] == '' for k in e if k.startswith('MAIL_')), e
    assert '/var/www/geheim' not in ziele(app)
    assert ma['environment']['WA_GEHEIM_DIR'] == '/var/www/geheim' and '/var/www/geheim' in ziele(ma) and 'WA_POSTAUSGANG' not in ma['environment']
elif was == 'datentrennung':
    # Datentrennung (ADR-007 Stufe 2): interner Ordner nur in app-mitarbeiter und postausgang – nie in der Kundenseite, nie im Web
    assert 'WA_DATEN_INTERN' not in app['environment'] and not [x for x in app.get('volumes', []) if 'daten-intern' in x.get('source', '')]
    assert ma['environment']['WA_DATEN_INTERN'] == '/var/www/daten-intern' and '/var/www/daten-intern' in ziele(ma)
    assert all(not x['target'].startswith('/var/www/html/') or x['target'] == '/var/www/html/data' for s2 in (ma, s['postausgang']) for x in s2['volumes'] if 'daten-intern' in x.get('source', ''))
elif was == 'postausgang-dienst':
    p = s['postausgang']; e = p['environment']
    assert p['image'] == app['image'] and p.get('pull_policy') == 'never' and not p.get('build') and p.get('user') == 'www-data'
    assert p.get('restart') == 'unless-stopped' and p['logging']['options']['max-size'] == '10m' and 'postausgang.php' in ' '.join(p['command'])
    assert 'postausgang.php' in ' '.join(p['healthcheck']['test']) and '--pruefen' in p['healthcheck']['test']
    assert not p.get('ports') and set(p['networks']) == {'postausgang'} and d['networks']['postausgang'].get('internal') is not True
    v = {x['target']: x for x in p['volumes']}
    assert set(v) == {'/var/www/html', '/var/www/html/data', '/var/www/geheim', '/var/www/daten-intern'} and v['/var/www/html']['read_only'] and v['/var/www/geheim']['read_only'], v
    assert e['WA_DATEN_INTERN'] == '/var/www/daten-intern'
    assert all(e.get(k) == basis['environment'][k] for k in basis['environment'] if k.startswith('MAIL_') or k == 'DOMAIN'), e
    assert e['WA_GEHEIM_DIR'] == '/var/www/geheim' and 'WA_POSTAUSGANG' not in e and not [k for k in e if k.startswith('OIDC_')]
    assert p.get('read_only') is True and 'no-new-privileges:true' in p.get('security_opt', []) and float(p['cpus']) > 0 and int(p['mem_limit']) > 0
PY
}
pruefe_json kunden-geheimnisse && ok "Kundenseite (app): keine Anmelde-Geheimnisse, kein Konten-Dienstkonto (ADR-007)" || nein "Kundenseite enthält Anmelde-Geheimnisse"
pruefe_json kunden-dateien && ok "Kundenseite (app): nur Anwendung und Datenordner, kein Dashboard, keine Keycloak-Hosts" || nein "Kundenseite: zusätzliche Dateien eingebunden"
pruefe_json kunden-netz && ok "Netze: Kundenseite nur mit Caddy (default); Mitarbeiter-Hosts und Keycloak im Netz intern" || nein "Netze der Container-Trennung"
pruefe_json kunden-haertung && ok "Kundenseite gehärtet: nur lesbar, /tmp und /run im Speicher, no-new-privileges, Grenzen für CPU/Speicher/Prozesse" || nein "Härtung der Kundenseite"
pruefe_json mitarbeiter-vollstaendig && ok "app-mitarbeiter: gleiches Image, alles aus docker-compose.yml plus Anmeldung, Dashboard, Karte" || nein "app-mitarbeiter unvollständig"
pruefe_json postausgang-kunde && ok "Postausgang: Kundenseite ohne Postfach-Werte und ohne Schlüsselordner, legt nur ab (ADR-007)" || nein "Postausgang: Kundenseite kennt das Postfach"
pruefe_json datentrennung && ok "Datentrennung: daten-intern nur in app-mitarbeiter und postausgang (außerhalb der Webwurzel), nie in der Kundenseite" || nein "Datentrennung: Einbindung von daten-intern"
pruefe_json postausgang-dienst && ok "Postausgang: eigener Dienst, gleiches Image, www-data, nur lesbar, kein Port, eigenes Netz, Postfach und Schlüssel nur lesend" || nein "Dienst postausgang"
rm -f "$MIT" "$OHNE"

# ── 3. Anwendungs-Image mit der Betriebskonfiguration ──
docker build -q -t stafl-app:pruefung "$REPO/deploy/image" >/dev/null
DATEN="$(mktemp -d)"; cp -r "$REPO/tests/fixtures/data-seed/." "$DATEN/"; chmod -R a+rwX "$DATEN"
docker run -d --name stafl-pruefung -p 127.0.0.1:18090:80 -p 127.0.0.1:18091:8090 \
  -e OIDC_ISSUER=https://login.dashboard-stafl.de/realms/mitarbeiter -e OIDC_SECRET_DASHBOARD=x -e OIDC_SECRET_ANGEBOT=x \
  -e OIDC_CRYPTO_DASHBOARD=pruefung-a -e OIDC_CRYPTO_ANGEBOT=pruefung-b -e OIDC_SECRET_VERWALTUNG=x -e OIDC_CRYPTO_VERWALTUNG=pruefung-c \
  -e OIDC_SECRET_BESTAND=x -e OIDC_CRYPTO_BESTAND=pruefung-d -e OIDC_SECRET_HR=x -e OIDC_CRYPTO_HR=pruefung-e -e OIDC_SECRET_CRM=x -e OIDC_CRYPTO_CRM=pruefung-f -e OIDC_SECRET_MARKETING=x -e OIDC_CRYPTO_MARKETING=pruefung-g -e OIDC_SECRET_SICHERHEIT=x -e OIDC_CRYPTO_SICHERHEIT=pruefung-t -e OIDC_SECRET_CONTROLLING=x -e OIDC_CRYPTO_CONTROLLING=pruefung-v -e OIDC_SECRET_LEERGUT=x -e OIDC_CRYPTO_LEERGUT=pruefung-x -e OIDC_SECRET_REWE=x -e OIDC_CRYPTO_REWE=pruefung-z -e OIDC_SECRET_QS=x -e OIDC_CRYPTO_QS=pruefung-q2 -e WA_EIGENE_ANMELDUNG=aus \
  -v "$REPO/app:/var/www/html:ro" -v "$DATEN:/var/www/html/data" -v "$REPO/dashboard:/var/www/dashboard:ro" \
  -v "$HIER/apache-oidc.conf:/etc/apache2/sites-enabled/zz-stafl-oidc.conf:ro" stafl-app:pruefung >/dev/null
for _ in $(seq 1 30); do curl -fsS -o /dev/null http://127.0.0.1:18090/ 2>/dev/null && break; sleep 1; done
docker exec stafl-pruefung apache2ctl -t 2>&1 | grep -q "Syntax OK" && ok "Apache-Konfiguration gültig" || nein "Apache-Konfiguration" "$(docker exec stafl-pruefung apache2ctl -t 2>&1 | tail -3)"
docker exec stafl-pruefung apache2ctl -M 2>/dev/null | grep -q auth_openidc && ok "mod_auth_openidc geladen" || nein "mod_auth_openidc nicht geladen"
code() { curl -s -o /dev/null -w '%{http_code}' -H "Host: $1" -H 'X-Forwarded-Proto: https' "${@:3}" "http://127.0.0.1:18090$2"; }
[ "$(code angebot-stafl.de /)" = 200 ] && ok "angebot-stafl.de: Startseite wie bisher" || nein "angebot-stafl.de Startseite" "$(code angebot-stafl.de /)"
[ "$(code angebot-stafl.de '/api/?action=kunde_status')" = 200 ] && ok "angebot-stafl.de: Schnittstelle wie bisher" || nein "angebot-stafl.de Schnittstelle"
antwort="$(curl -s -H 'Host: angebot-stafl.de' -H 'Content-Type: application/json' -d '{"username":"x","password":"y"}' 'http://127.0.0.1:18090/api/?action=kunde_login')"
echo "$antwort" | grep -q "nicht korrekt" && ok "angebot-stafl.de: Kundenanmeldung unverändert (keine Keycloak-Sperre)" || nein "angebot-stafl.de Kundenanmeldung" "$antwort"
antwort="$(curl -s -w ' %{http_code}' -H 'Host: angebot-stafl.de' -H 'Content-Type: application/json' -d '{"username":"admin","password":"y"}' 'http://127.0.0.1:18090/api/?action=login')"
case "$antwort" in *umgezogen*" 410") ok "angebot-stafl.de: alter Eingabebereich stillgelegt (Mitarbeiteranmeldung 410, Verweis auf die neue Adresse)";; *) nein "angebot-stafl.de: Mitarbeiteranmeldung" "$antwort";; esac
curl -s -H 'Host: angebot-stafl.de' 'http://127.0.0.1:18090/api/?action=status' | grep -q '"ok":true.*"umgezogen":"https://angebot.dashboard-stafl.de/admin/"' \
  && ok "angebot-stafl.de: Status für den Healthcheck weiter erreichbar" || nein "angebot-stafl.de Status"
[ "$(code angebot-stafl.de /dashboard/)" = 404 ] && ok "angebot-stafl.de: kein Dashboard" || nein "Dashboard auf angebot-stafl.de" "$(code angebot-stafl.de /dashboard/)"
[ "$(code unbekannt.example /)" = 200 ] && ok "unbekannter Host fällt auf den bisherigen Standard zurück" || nein "Standard-Host"
for h in dashboard-stafl.de angebot.dashboard-stafl.de verwaltung.dashboard-stafl.de bestand.dashboard-stafl.de hr.dashboard-stafl.de crm.dashboard-stafl.de marketing.dashboard-stafl.de sicherheit.dashboard-stafl.de controlling.dashboard-stafl.de leergut.dashboard-stafl.de rewe.dashboard-stafl.de qs.dashboard-stafl.de; do
  c="$(code "$h" '/api/?action=status')"; [ "$c" = 401 ] && ok "$h: Schnittstelle ohne Anmeldung 401" || nein "$h Schnittstelle ohne Anmeldung" "$c"
  c="$(code "$h" '/api/?action=login' -H 'Content-Type: application/json' -d '{}')"; [ "$c" = 401 ] && ok "$h: eigene Anmeldung nicht erreichbar" || nein "$h Anmeldung" "$c"
  c="$(code "$h" /admin/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "$h: Eingabebereich nur über Keycloak ($c, ohne Keycloak hier nicht erreichbar)";; *) nein "$h Eingabebereich" "$c";; esac
  c="$(code "$h" /dashboard/abgemeldet.html)"; [ "$c" = 200 ] && ok "$h: Abmeldeseite öffentlich" || nein "$h Abmeldeseite" "$c"
done
# Anmeldeseite: Prüfung vor Keycloak (Caddy forward_auth, Aktion anmeldung_pruefen) – ohne OIDC, sonst nichts aus der Anwendung
c="$(code login.dashboard-stafl.de '/api/index.php?action=anmeldung_pruefen')"; [ "$c" = 200 ] && ok "login.dashboard-stafl.de: Prüfung vor der Anmeldung erreichbar (200)" || nein "login.dashboard-stafl.de Prüfung vor der Anmeldung" "$c"
for p in / /admin/ /assets/app.css /module/sicherheit/; do
  c="$(code login.dashboard-stafl.de "$p")"; [ "$c" = 403 ] && ok "login.dashboard-stafl.de$p: in der Anwendung gesperrt (403)" || nein "login.dashboard-stafl.de$p" "$c"
done
c="$(code login.dashboard-stafl.de '/api/index.php?action=users')"; [ "$c" = 404 ] && ok "login.dashboard-stafl.de: andere Aktionen gibt es dort nicht (404)" || nein "login.dashboard-stafl.de andere Aktion" "$c"
c="$(code dashboard-stafl.de '/api/?action=anmeldung_pruefen')"; [ "$c" = 401 ] && ok "dashboard-stafl.de: Prüfung der Anmeldeseite nicht ohne Anmeldung (401)" || nein "dashboard-stafl.de anmeldung_pruefen" "$c"
c="$(code angebot-stafl.de '/api/?action=anmeldung_pruefen')"; [ "$c" != 200 ] && ok "angebot-stafl.de: Prüfung der Anmeldeseite nicht beantwortet ($c)" || nein "angebot-stafl.de anmeldung_pruefen" "$c"
# Notzugang (Port 8090, ADR-007 Regel 6): ohne WA_NOTZUGANG=an geschlossen wie angebot-stafl.de; http ohne upgrade-insecure-requests
antwort="$(curl -s -w ' %{http_code}' -H 'Content-Type: application/json' -d '{"username":"admin","password":"y"}' 'http://127.0.0.1:18091/api/?action=login')"
case "$antwort" in *umgezogen*" 410") ok "Notzugang (Port 8090): ohne WA_NOTZUGANG=an geschlossen (410)";; *) nein "Notzugang geschlossen" "$antwort";; esac
kopf="$(curl -s -D - -o /dev/null 'http://127.0.0.1:18091/admin/')"
echo "$kopf" | head -1 | grep -q ' 200' && ! echo "$kopf" | grep -i '^content-security-policy:' | grep -qi 'upgrade-insecure-requests' \
  && ok "Notzugang: Eingabebereich über http erreichbar, ohne upgrade-insecure-requests" || nein "Notzugang: Kopfzeilen" "$kopf"
kopf="$(curl -s -D - -o /dev/null -H 'Host: angebot-stafl.de' 'http://127.0.0.1:18090/admin/')"
if docker exec stafl-pruefung apache2ctl -M 2>/dev/null | grep -q headers_module; then
  echo "$kopf" | grep -i '^content-security-policy:' | grep -qi 'upgrade-insecure-requests' && ok "angebot-stafl.de: CSP der Anwendung unverändert (mit upgrade-insecure-requests)" || nein "angebot-stafl.de: CSP" "$kopf"
fi
# Startadressen je Host (ohne Anmeldung nur die Weiterleitung, nichts aus der Anwendung): Bestand → /admin/, Import → Ansicht importe
ziel() { curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -H "Host: $1" -H 'X-Forwarded-Proto: https' "http://127.0.0.1:18090$2"; }
case "$(ziel bestand.dashboard-stafl.de /)" in "302 "*/admin/) ok "bestand.dashboard-stafl.de: Startadresse führt in den Eingabebereich";; *) nein "bestand.dashboard-stafl.de Startadresse" "$(ziel bestand.dashboard-stafl.de /)";; esac
for p in /import/ /import; do
  case "$(ziel verwaltung.dashboard-stafl.de "$p")" in "302 "*"/admin/?ansicht=importe&nur=import") ok "verwaltung.dashboard-stafl.de$p: Importzentrale (Ansicht importe)";; *) nein "verwaltung.dashboard-stafl.de$p" "$(ziel verwaltung.dashboard-stafl.de "$p")";; esac
done
# HR: Startadresse und Eingabebereich führen zur Urlaubsverwaltung; die Seite selbst nur über Keycloak
for p in / /admin/ /admin; do
  case "$(ziel hr.dashboard-stafl.de "$p")" in "302 "*/module/hr/) ok "hr.dashboard-stafl.de$p: führt zur Urlaubsverwaltung (/module/hr/)";; *) nein "hr.dashboard-stafl.de$p" "$(ziel hr.dashboard-stafl.de "$p")";; esac
done
c="$(code hr.dashboard-stafl.de /module/hr/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "hr.dashboard-stafl.de: Urlaubsverwaltung nur über Keycloak ($c)";; *) nein "hr.dashboard-stafl.de/module/hr/" "$c";; esac
c="$(code hr.dashboard-stafl.de /assets/app.css)"; [ "$c" = 200 ] && ok "hr.dashboard-stafl.de: Stylesheets ohne Anmeldung (Abmeldeseite)" || nein "hr.dashboard-stafl.de /assets/" "$c"
# CRM: Startadresse und Eingabebereich führen zum CRM; die Seite selbst nur über Keycloak
for p in / /admin/ /admin; do
  case "$(ziel crm.dashboard-stafl.de "$p")" in "302 "*/module/crm/) ok "crm.dashboard-stafl.de$p: führt zum CRM (/module/crm/)";; *) nein "crm.dashboard-stafl.de$p" "$(ziel crm.dashboard-stafl.de "$p")";; esac
done
c="$(code crm.dashboard-stafl.de /module/crm/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "crm.dashboard-stafl.de: CRM nur über Keycloak ($c)";; *) nein "crm.dashboard-stafl.de/module/crm/" "$c";; esac
c="$(code crm.dashboard-stafl.de /assets/app.css)"; [ "$c" = 200 ] && ok "crm.dashboard-stafl.de: Stylesheets ohne Anmeldung (Abmeldeseite)" || nein "crm.dashboard-stafl.de /assets/" "$c"
# Marketing: Startadresse und Eingabebereich führen zum Redaktionsplan; die Seite selbst nur über Keycloak
for p in / /admin/ /admin; do
  case "$(ziel marketing.dashboard-stafl.de "$p")" in "302 "*/module/marketing/) ok "marketing.dashboard-stafl.de$p: führt zum Redaktionsplan (/module/marketing/)";; *) nein "marketing.dashboard-stafl.de$p" "$(ziel marketing.dashboard-stafl.de "$p")";; esac
done
c="$(code marketing.dashboard-stafl.de /module/marketing/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "marketing.dashboard-stafl.de: Redaktionsplan nur über Keycloak ($c)";; *) nein "marketing.dashboard-stafl.de/module/marketing/" "$c";; esac
c="$(code marketing.dashboard-stafl.de /assets/app.css)"; [ "$c" = 200 ] && ok "marketing.dashboard-stafl.de: Stylesheets ohne Anmeldung (Abmeldeseite)" || nein "marketing.dashboard-stafl.de /assets/" "$c"
# Sicherheit: Startadresse und Eingabebereich führen zur Sicherheitszentrale; die Seite selbst nur über Keycloak
for p in / /admin/ /admin; do
  case "$(ziel sicherheit.dashboard-stafl.de "$p")" in "302 "*/module/sicherheit/) ok "sicherheit.dashboard-stafl.de$p: führt zur Sicherheitszentrale (/module/sicherheit/)";; *) nein "sicherheit.dashboard-stafl.de$p" "$(ziel sicherheit.dashboard-stafl.de "$p")";; esac
done
c="$(code sicherheit.dashboard-stafl.de /module/sicherheit/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "sicherheit.dashboard-stafl.de: Sicherheitszentrale nur über Keycloak ($c)";; *) nein "sicherheit.dashboard-stafl.de/module/sicherheit/" "$c";; esac
# Controlling: Startadresse und Eingabebereich führen zum Controlling; die Seite selbst nur über Keycloak
for p in / /admin/ /admin; do
  case "$(ziel controlling.dashboard-stafl.de "$p")" in "302 "*/module/controlling/) ok "controlling.dashboard-stafl.de$p: führt zum Controlling (/module/controlling/)";; *) nein "controlling.dashboard-stafl.de$p" "$(ziel controlling.dashboard-stafl.de "$p")";; esac
done
c="$(code controlling.dashboard-stafl.de /module/controlling/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "controlling.dashboard-stafl.de: Controlling nur über Keycloak ($c)";; *) nein "controlling.dashboard-stafl.de/module/controlling/" "$c";; esac
# Leergut: Startadresse und Eingabebereich führen zum Leergut; die Seite selbst nur über Keycloak
for p in / /admin/ /admin; do
  case "$(ziel leergut.dashboard-stafl.de "$p")" in "302 "*/module/leergut/) ok "leergut.dashboard-stafl.de$p: führt zum Leergut (/module/leergut/)";; *) nein "leergut.dashboard-stafl.de$p" "$(ziel leergut.dashboard-stafl.de "$p")";; esac
done
c="$(code leergut.dashboard-stafl.de /module/leergut/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "leergut.dashboard-stafl.de: Leergut nur über Keycloak ($c)";; *) nein "leergut.dashboard-stafl.de/module/leergut/" "$c";; esac
# REWE: Startadresse und Eingabebereich führen zum REWE-Modul; die Seite selbst nur über Keycloak
for p in / /admin/ /admin; do
  case "$(ziel rewe.dashboard-stafl.de "$p")" in "302 "*/module/rewe/) ok "rewe.dashboard-stafl.de$p: führt zum REWE-Modul (/module/rewe/)";; *) nein "rewe.dashboard-stafl.de$p" "$(ziel rewe.dashboard-stafl.de "$p")";; esac
done
c="$(code rewe.dashboard-stafl.de /module/rewe/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "rewe.dashboard-stafl.de: REWE nur über Keycloak ($c)";; *) nein "rewe.dashboard-stafl.de/module/rewe/" "$c";; esac
# Qualitätssicherung: Startadresse und Eingabebereich führen zum QM-System; die Seite selbst nur über Keycloak
for p in / /admin/ /admin; do
  case "$(ziel qs.dashboard-stafl.de "$p")" in "302 "*/module/qs/) ok "qs.dashboard-stafl.de$p: führt zum QM-System (/module/qs/)";; *) nein "qs.dashboard-stafl.de$p" "$(ziel qs.dashboard-stafl.de "$p")";; esac
done
c="$(code qs.dashboard-stafl.de /module/qs/ -H 'Accept: text/html')"; case "$c" in 302|500|502|503) ok "qs.dashboard-stafl.de: QM-System nur über Keycloak ($c)";; *) nein "qs.dashboard-stafl.de/module/qs/" "$c";; esac
case "$(ziel angebot.dashboard-stafl.de /import/)" in *ansicht=importe*) nein "angebot.dashboard-stafl.de/import/ leitet in die Importzentrale" "$(ziel angebot.dashboard-stafl.de /import/)";; *) ok "Import-Adresse nur auf dem Verwaltungs-Host";; esac
docker logs stafl-pruefung 2>&1 | grep -iE "AH0|error" | grep -viE "metadata|oidc_provider_static_config|oidc_util_http|curl" | head -3 | sed 's/^/Info: /' || true

# ── 3a. Zwei Anwendungs-Container wie im Betrieb (ADR-007): Compose mit Ergänzungsdatei, Image von oben ──
# Startet app (Kundenseite) und app-mitarbeiter in einem Wegwerf-Projekt – ohne Caddy und Keycloak – und prüft von innen:
# Trennung der Netze, keine Anmelde-Geheimnisse auf der Kundenseite, nur lesbares Dateisystem, Datenordner beschreibbar.
APP2="$(mktemp -d)"; APPPROJ=stafl-apppruefung
# Aufräumen: Dateien, die die Anwendung als www-data in daten/ angelegt hat, darf der Nutzer des Prüflaufs nicht löschen –
# daher über einen Wegwerf-Container desselben Images; Reste in /tmp brechen die Prüfung nie ab
app2_ende() {
  (cd "$APP2" && docker compose -p "$APPPROJ" down -v >/dev/null 2>&1) || true
  docker run --rm -v "$APP2/daten:/d" stafl-app:pruefung sh -c 'rm -rf /d/* /d/.[!.]*' >/dev/null 2>&1 || true
  rm -rf "$APP2" 2>/dev/null || true
}
mkdir -p "$APP2/deploy/anmeldung" "$APP2/daten" "$APP2/daten-karte" "$APP2/daten-geheim" "$APP2/daten-intern"
cp "$REPO/docker-compose.yml" "$APP2/"; cp "$HIER/docker-compose.anmeldung.yml" "$HIER/apache-oidc.conf" "$APP2/deploy/anmeldung/"
cp -r "$REPO/deploy/image" "$APP2/deploy/"; cp -r "$REPO/app" "$REPO/dashboard" "$APP2/"
cp -r "$REPO/tests/fixtures/data-seed/." "$APP2/daten/"; chmod -R a+rwX "$APP2/daten" "$APP2/daten-geheim" "$APP2/daten-intern"; chmod -R a+rX "$APP2/app" "$APP2/dashboard" "$APP2/deploy"
{ cat "$ENV"; printf 'STAFL_APP_VERSION=pruefung\nKUNDEN_CPUS=1\nKUNDEN_SPEICHER=512m\nNOTZUGANG_PORT=18192\n'; } > "$APP2/.env"
dc2() { (cd "$APP2" && docker compose -p "$APPPROJ" -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml "$@"); }
# Abruf im Container (ohne veröffentlichte Ports): dienst host pfad [methode] [inhalt] → „Status Antwortanfang“
abruf() { dc2 exec -T "$1" php -r '
  $o = ["http" => ["method" => $argv[3] ?: "GET", "ignore_errors" => true, "follow_location" => 0, "content" => $argv[4],
        "header" => "Host: " . $argv[1] . "\r\nX-Forwarded-Proto: https\r\nContent-Type: application/json\r\n"]];
  $b = @file_get_contents("http://127.0.0.1" . $argv[2], false, stream_context_create($o));
  echo preg_match("#^HTTP/\S+ (\d{3})#", $http_response_header[0] ?? "", $m) ? $m[1] : "000", " ", substr((string)$b, 0, 400);' -- "$2" "$3" "${4:-GET}" "${5:-}" 2>/dev/null; }
if dc2 up -d --no-build app app-mitarbeiter postausgang >/tmp/app2-start.txt 2>&1; then
  for _ in $(seq 1 30); do case "$(abruf app angebot-stafl.de /)" in 200*) break;; esac; sleep 1; done
  case "$(abruf app angebot-stafl.de /)" in 200*) ok "app (Kundenseite) startet mit nur lesbarem Dateisystem und liefert die Startseite";; *) nein "app startet nicht" "$(dc2 logs --tail 20 app 2>&1)";; esac
  case "$(abruf app angebot-stafl.de '/api/?action=kunde_login' POST '{"username":"x","password":"y"}')" in 401*"nicht korrekt"*) ok "app: Kundenanmeldung antwortet (Fehlversuch im Datenordner vermerkt)";; *) nein "app: Kundenanmeldung" "$(abruf app angebot-stafl.de '/api/?action=kunde_login' POST '{"username":"x","password":"y"}')";; esac
  case "$(abruf app angebot-stafl.de '/api/?action=login' POST '{"username":"admin","password":"y"}')" in 410*umgezogen*) ok "app: Mitarbeiteranmeldung stillgelegt (410)";; *) nein "app: Mitarbeiteranmeldung" "$(abruf app angebot-stafl.de '/api/?action=login' POST '{}')";; esac
  case "$(abruf app angebot-stafl.de '/api/?action=users')" in 410*) ok "app: Mitarbeiter-Aktionen nicht ausführbar (410)";; *) nein "app: Mitarbeiter-Aktion" "$(abruf app angebot-stafl.de '/api/?action=users')";; esac
  ! dc2 exec -T app apache2ctl -S 2>/dev/null | grep -q dashboard-stafl.de && ok "app: keine Keycloak-Hosts in Apache" || nein "app kennt Keycloak-Hosts"
  [ "$(dc2 exec -T app env | grep -cE '^(OIDC_|WA_KONTEN)')" = 0 ] && ok "app: keine Anmelde-Geheimnisse in der Umgebung" || nein "app: Anmelde-Geheimnisse in der Umgebung"
  ! dc2 exec -T app sh -c 'touch /usr/local/probe' 2>/dev/null && ! dc2 exec -T -u www-data app sh -c 'touch /var/www/html/probe' 2>/dev/null \
    && ok "app: Dateisystem und Anwendung nicht beschreibbar (auch nicht für root)" || nein "app: Dateisystem beschreibbar"
  dc2 exec -T -u www-data app sh -c 'touch /var/www/html/data/.probe && rm /var/www/html/data/.probe && touch /tmp/.probe' 2>/dev/null \
    && ok "app: Datenordner und /tmp beschreibbar" || nein "app: Datenordner oder /tmp nicht beschreibbar"
  dc2 exec -T app php -r 'exit(gethostbynamel("app-mitarbeiter") === false && gethostbynamel("keycloak") === false ? 0 : 1);' 2>/dev/null \
    && ok "app: app-mitarbeiter und Keycloak im Netz nicht erreichbar" || nein "app erreicht app-mitarbeiter bzw. Keycloak"
  ID=$(dc2 ps -q app)
  docker inspect -f '{{json .HostConfig.ReadonlyRootfs}} {{json .HostConfig.SecurityOpt}} {{json .HostConfig.Memory}} {{json .HostConfig.NanoCpus}} {{json .HostConfig.PidsLimit}}' "$ID" \
    | grep -qE '^true \["no-new-privileges:true"\] [1-9][0-9]* [1-9][0-9]* [1-9][0-9]*$' && ok "app: Grenzen und no-new-privileges wirksam" \
    || nein "app: Grenzen" "$(docker inspect -f '{{json .HostConfig.ReadonlyRootfs}} {{json .HostConfig.SecurityOpt}} {{json .HostConfig.Memory}} {{json .HostConfig.NanoCpus}} {{json .HostConfig.PidsLimit}}' "$ID")"
  for _ in $(seq 1 30); do case "$(abruf app-mitarbeiter dashboard-stafl.de '/api/?action=status')" in 401*) break;; esac; sleep 1; done
  case "$(abruf app-mitarbeiter dashboard-stafl.de '/api/?action=status')" in 401*) ok "app-mitarbeiter: Mitarbeiter-Hosts nur mit Anmeldung (401)";; *) nein "app-mitarbeiter: dashboard-stafl.de" "$(abruf app-mitarbeiter dashboard-stafl.de '/api/?action=status') $(dc2 logs --tail 20 app-mitarbeiter 2>&1)";; esac
  [ "$(dc2 exec -T app-mitarbeiter env | grep -c '^OIDC_SECRET_KONTEN=')" = 1 ] && ok "app-mitarbeiter: Anmelde-Geheimnisse und Konten-Dienstkonto vorhanden" || nein "app-mitarbeiter ohne Anmelde-Geheimnisse"
  # Postausgang von innen (ADR-007): Dienst läuft (Lebenszeichen), ist abgeschottet; die Kundenseite kennt kein Postfach
  for _ in $(seq 1 30); do dc2 exec -T postausgang php /var/www/html/api/postausgang.php --pruefen >/dev/null 2>&1 && break; sleep 1; done
  dc2 exec -T postausgang php /var/www/html/api/postausgang.php --pruefen >/dev/null 2>&1 && ok "postausgang: Dienst läuft (frisches Lebenszeichen im Datenordner)" \
    || nein "postausgang läuft nicht" "$(dc2 logs --tail 20 postausgang 2>&1)"
  [ "$(dc2 exec -T postausgang id -un 2>/dev/null)" = www-data ] && ! dc2 exec -T postausgang sh -c 'touch /var/www/html/probe || touch /var/www/geheim/probe' 2>/dev/null \
    && ok "postausgang: als www-data, Anwendung und Schlüsselordner nur lesbar" || nein "postausgang: Nutzer oder Schreibrechte"
  dc2 exec -T postausgang php -r 'exit(gethostbynamel("app-mitarbeiter") === false && gethostbynamel("keycloak") === false && gethostbynamel("app") === false ? 0 : 1);' 2>/dev/null \
    && ok "postausgang: weder Apps noch Keycloak im Netz erreichbar" || nein "postausgang erreicht andere Dienste"
  dc2 exec -T app sh -c 'test -z "$MAIL_SMTP_PASS$MAIL_SMTP_HOST" && test "$WA_POSTAUSGANG" = warteschlange && test ! -e /var/www/geheim' 2>/dev/null \
    && ok "app: kein Postfach in der Umgebung, kein Schlüsselordner, Versand nur über den Postausgang" || nein "app kennt das Postfach"
  dc2 exec -T app sh -c 'test ! -e /var/www/daten-intern && test -z "${WA_DATEN_INTERN:-}"' 2>/dev/null \
    && [ "$(dc2 exec -T app-mitarbeiter sh -c 'test -d /var/www/daten-intern && echo "$WA_DATEN_INTERN"' 2>/dev/null)" = /var/www/daten-intern ] \
    && ok "Datentrennung: daten-intern nur in app-mitarbeiter (Kundenseite ohne Ordner und ohne WA_DATEN_INTERN)" || nein "Datentrennung: Einbindung im Container"
  case "$(abruf app angebot-stafl.de '/api/postausgang.php')" in 404*) ok "app: Postausgang-Skript nicht über den Webserver aufrufbar (404)";; *) nein "app: api/postausgang.php erreichbar" "$(abruf app angebot-stafl.de '/api/postausgang.php')";; esac
  # Notzugang (ADR-007 Regel 6): geschlossen im Normalbetrieb; nach WA_NOTZUGANG=an nur über 127.0.0.1 offen – die Kundenseite
  # öffnet ihn auch mit der früheren Zeile WA_EIGENE_ANMELDUNG=an nicht mehr
  [ "$(docker port "$(dc2 ps -q app-mitarbeiter)" 8090/tcp 2>/dev/null)" = "127.0.0.1:18192" ] && ok "app-mitarbeiter: Notzugang nur auf 127.0.0.1 veröffentlicht" \
    || nein "app-mitarbeiter: Port des Notzugangs" "$(docker port "$(dc2 ps -q app-mitarbeiter)" 2>&1)"
  case "$(curl -s -w ' %{http_code}' -H 'Content-Type: application/json' -d '{"username":"admin","password":"y"}' 'http://127.0.0.1:18192/api/?action=login')" in
    *umgezogen*" 410") ok "Notzugang im Normalbetrieb geschlossen (410)";; *) nein "Notzugang im Normalbetrieb" "$(curl -s 'http://127.0.0.1:18192/api/?action=status')";; esac
  printf 'WA_NOTZUGANG=an\nWA_EIGENE_ANMELDUNG=an\n' >> "$APP2/.env"
  dc2 up -d --no-build app app-mitarbeiter >/dev/null 2>&1
  for _ in $(seq 1 30); do case "$(curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:18192/api/?action=status')" in 200) break;; esac; sleep 1; done
  antwort="$(curl -s -w ' %{http_code}' -H 'Content-Type: application/json' -d '{"username":"admin","password":"falsch"}' 'http://127.0.0.1:18192/api/?action=login')"
  # ohne Nutzer in den Testdaten antwortet die alte Anmeldung mit 409 (kein Zugang vorhanden), sonst 401 – nicht 410 (stillgelegt)
  case "$antwort" in *umgezogen*) nein "Notzugang offen" "$antwort";; *" 401"|*" 409") ok "Notzugang mit WA_NOTZUGANG=an: alte Anmeldung über den Tunnel erreichbar (${antwort##* })";; *) nein "Notzugang offen" "$antwort";; esac
  case "$(curl -s -w ' %{http_code}' -H 'X-Forwarded-For: 203.0.113.9' -H 'Content-Type: application/json' -d '{"username":"admin","password":"falsch"}' 'http://127.0.0.1:18192/api/?action=login')" in
    *umgezogen*" 410") ok "Notzugang: mit weitergereichter Besucheradresse (nicht über den Tunnel) geschlossen";; *) nein "Notzugang mit X-Forwarded-For";; esac
  case "$(abruf app angebot-stafl.de '/api/?action=login' POST '{"username":"admin","password":"y"}')" in 410*umgezogen*) ok "app: auch mit WA_EIGENE_ANMELDUNG=an in .env stillgelegt (410)";; *) nein "app mit WA_EIGENE_ANMELDUNG=an" "$(abruf app angebot-stafl.de '/api/?action=login' POST '{}')";; esac
  case "$(abruf app-mitarbeiter angebot-stafl.de '/api/?action=login' POST '{"username":"admin","password":"y"}')" in 410*umgezogen*) ok "app-mitarbeiter: Standard-Host (Port 80) bleibt stillgelegt, auch bei offenem Notzugang";; *) nein "app-mitarbeiter Standard-Host" "$(abruf app-mitarbeiter angebot-stafl.de '/api/?action=login' POST '{}')";; esac
else
  nein "Anwendungs-Container starten nicht" "$(tail -5 /tmp/app2-start.txt)"
fi
app2_ende

# ── 3b. Keycloak wirklich starten (wie auf dem Server): mit Start-Konto, dann ohne (nach konten.sh verwaltung) neu ──
KCP="$(mktemp -d)"; KCPROJ=stafl-kcpruefung
kc_ende() { (cd "$KCP" && docker compose -p "$KCPROJ" down -v >/dev/null 2>&1); rm -rf "$KCP"; }
mkdir -p "$KCP/deploy/anmeldung"
cp "$REPO/docker-compose.yml" "$KCP/"; cp "$HIER/docker-compose.anmeldung.yml" "$HIER/realm-mitarbeiter.json" "$HIER/einrichten.sh" "$KCP/deploy/anmeldung/"
# Design der Anmeldeseite (Volume, nur lesend): Quelle muss existieren, sonst legt Docker sie als root-eigenen Leerordner an
cp -r "$HIER/theme" "$KCP/deploy/anmeldung/"; chmod -R a+rX "$KCP/deploy/anmeldung/theme"
printf 'DOMAIN=angebot-stafl.de\nCOMPOSE_FILE=docker-compose.yml:deploy/anmeldung/docker-compose.anmeldung.yml\n' > "$KCP/.env"
(cd "$KCP" && sh deploy/anmeldung/einrichten.sh >/dev/null)
# einrichten.sh übergibt den Realm-Import nur als root an den Keycloak-Benutzer (1000); ohne root (CI) diese Wegwerf-Kopie freigeben
[ "$(id -u)" = 0 ] || chmod -R a+rX "$KCP/daten-anmeldung/realm-import" "$KCP/daten-anmeldung/vault"
# bis 400 s: der erste Start (Datenbank anlegen, Indizes prüfen) dauert auf CI-Rechnern deutlich länger
kc_bereit() { for _ in $(seq 1 200); do curl -fsS -o /dev/null http://127.0.0.1:8180/realms/mitarbeiter/.well-known/openid-configuration 2>/dev/null && return 0; sleep 2; done; return 1; }
if (cd "$KCP" && docker compose -p "$KCPROJ" up -d keycloak-db keycloak >/dev/null 2>&1) && kc_bereit; then
  ok "Keycloak startet mit Start-Konto (Ersteinrichtung)"
  START_PW=$(sed -n 's/^KC_BOOTSTRAP_ADMIN_PASSWORD=//p' "$KCP/daten-anmeldung/einrichtung.env")
  curl -fsS -d grant_type=password -d client_id=admin-cli -d username=einrichtung --data-urlencode "password=$START_PW" \
    http://127.0.0.1:8180/realms/master/protocol/openid-connect/token 2>/dev/null | grep -q access_token \
    && ok "Start-Konto aus daten-anmeldung/einrichtung.env funktioniert" || nein "Start-Konto"
else
  nein "Keycloak startet nicht (Ersteinrichtung)" "$(cd "$KCP" && docker compose -p "$KCPROJ" logs --tail 15 keycloak 2>&1)"
fi
rm -f "$KCP/daten-anmeldung/einrichtung.env"   # wie nach konten.sh verwaltung
if (cd "$KCP" && docker compose -p "$KCPROJ" up -d --force-recreate keycloak >/dev/null 2>&1) && sleep 5 && kc_bereit \
  && [ -z "$(cd "$KCP" && docker compose -p "$KCPROJ" exec -T keycloak env | grep '^KC_BOOTSTRAP')" ]; then
  ok "Keycloak startet nach der Einrichtung ohne Start-Konto neu (keine leeren KC_BOOTSTRAP-Variablen)"
  (cd "$KCP" && docker compose -p "$KCPROJ" exec -T keycloak test -r /opt/keycloak/themes/stafl/login/theme.properties) \
    && ok "Design der Anmeldeseite im Container (Theme stafl, nur lesend eingebunden)" || nein "Design der Anmeldeseite fehlt im Container"
else
  nein "Keycloak startet nach der Einrichtung nicht neu" "$(cd "$KCP" && docker compose -p "$KCPROJ" logs --tail 15 keycloak 2>&1)"
fi
kc_ende

# ── 4. Caddy ──
CADDY_IMAGE=$(sed -n 's/^ *image: *\(caddy:[^ ]*\).*$/\1/p' "$REPO/docker-compose.yml")   # dieselbe Fassung wie im Betrieb
if docker run --rm -e DOMAIN=angebot-stafl.de -v "$REPO/Caddyfile:/etc/caddy/Caddyfile:ro" "$CADDY_IMAGE" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/tmp/caddy-pruefung.txt 2>&1; then
  ok "Caddyfile mit den Anmelde-Hosts gültig"
else
  nein "Caddyfile" "$(tail -3 /tmp/caddy-pruefung.txt)"
fi
exit $FEHLER
