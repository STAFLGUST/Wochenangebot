#!/bin/sh
# Netzsperre am Server: Port 80 und 443 nehmen nur noch Verbindungen von den Edge-Servern von bunny.net an (nftables).
# Ergänzt die Sperre per Schlüssel (CDN_PFLICHT=1, Caddy antwortet 403): Wer bunny umgeht, erreicht Caddy gar nicht erst.
# Anleitung und Rückweg: docs/bunny-cdn.md, Abschnitt 7. Als root im Installationsordner ausführen:
#
#   sh deploy/cdn-netzsperre.sh status        # Modus, Liste, Zähler, fremde Verbindungsversuche der letzten 24 Stunden
#   sh deploy/cdn-netzsperre.sh beobachten    # Regeln setzen, die nur zählen und protokollieren (zuerst 1–2 Tage)
#   sh deploy/cdn-netzsperre.sh an            # fremde Verbindungen verwerfen; Probe über bunny, sonst zurück auf beobachten
#   sh deploy/cdn-netzsperre.sh aus           # Notfall/Rückweg: Regeln und Timer entfernen, Port 443 wieder für alle offen
#   sh deploy/cdn-netzsperre.sh aktualisieren # vom Timer (alle 30 Minuten): Liste höchstens alle 6 Stunden holen, Regeln setzen
#
# Liste: api.bunny.net (IPv4 und IPv6), geprüft und mit der bisherigen zusammengeführt (deploy/cdn_netzsperre.py; eine
# Adresse bleibt 14 Tage nach dem letzten Erscheinen). Eigene Tabelle „inet stafl_netzsperre“ neben den Regeln von Docker,
# nur für die Schnittstelle der Standardroute – Abrufe vom Server selbst (127.0.0.1, Healthcheck) und Verbindungen nach außen
# bleiben unberührt, ebenso die Hostinger-Browserkonsole. Root-Dateien im Installationsordner (nie in daten/):
# .cdn-netzsperre (Modus), .cdn-netzsperre-liste.json (Liste), .cdn-netzsperre-regeln (Prüfsumme und Zeit der gesetzten Regeln).
set -eu
umask 077
BASIS=${WA_BASIS:-$(pwd)}
HIER=$(cd "$(dirname "$0")" && pwd)
ENV="$BASIS/.env"
MODUS_DATEI="$BASIS/.cdn-netzsperre"
LISTE="$BASIS/.cdn-netzsperre-liste.json"
STAND="$BASIS/.cdn-netzsperre-regeln"
NFT=${WA_NFT:-nft}
SYSTEMCTL=${WA_SYSTEMCTL:-systemctl}
IPBEFEHL=${WA_IP:-ip}
JOURNAL=${WA_JOURNAL:-journalctl}
CURL=${WA_CURL:-curl}
UNITS=${WA_UNITS:-/etc/systemd/system}
PAUSE=${WA_PAUSE:-5}
TABELLE="inet stafl_netzsperre"
TIMER=wochenangebot-netzsperre
py() { python3 "$HIER/cdn_netzsperre.py" "$@"; }
envwert() { sed -n "s/^$1=//p" "$ENV" 2>/dev/null | tail -1 | tr -d '"'"'"' '; }
modus() { m=$(cat "$MODUS_DATEI" 2>/dev/null || true); case "$m" in beobachten|an) echo "$m" ;; *) echo aus ;; esac; }
tabelle_da() { $NFT list table $TABELLE >/dev/null 2>&1; }
schnittstelle() {
  s=$($IPBEFEHL -o route show default 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "dev") { print $(i + 1); exit }}')
  case "$s" in ''|*[!A-Za-z0-9_.-]*) return 1 ;; *) echo "$s" ;; esac
}

[ "$(id -u)" = 0 ] || [ -n "${WA_OHNE_ROOT:-}" ] || { echo "Abbruch: als root ausführen." >&2; exit 1; }
BEFEHL=${1:-status}

# Regeln für den Modus setzen – nur, wenn sie sich geändert haben oder fehlen (sonst bleiben die Zähler erhalten).
anwenden() {
  m=$1
  wo=$(schnittstelle) || { echo "Keine Standardroute gefunden – Regeln unverändert." >&2; return 1; }
  tmp=$(mktemp "$BASIS/.cdn-netzsperre-nft.XXXXXX")
  if ! py regelwerk "$LISTE" "$m" "$wo" > "$tmp"; then
    rm -f "$tmp"; echo "Regeln unverändert (keine nutzbare Liste)." >&2; return 1
  fi
  summe=$(sha256sum "$tmp" | cut -d' ' -f1)
  if tabelle_da && [ "$(cut -d' ' -f1 "$STAND" 2>/dev/null || true)" = "$summe" ]; then rm -f "$tmp"; return 0; fi
  if ! $NFT -f "$tmp"; then rm -f "$tmp"; echo "nft hat die Regeln abgelehnt – bisheriger Stand bleibt." >&2; return 1; fi
  rm -f "$tmp"
  echo "$summe $(date -u +%Y-%m-%dT%H:%M:%SZ) $m $wo" > "$STAND"
  echo "Netzsperre gesetzt: Modus $m, Schnittstelle $wo."
}

entfernen() {
  if tabelle_da; then $NFT delete table $TABELLE; fi
  rm -f "$STAND"
}

timer_einrichten() {
  cat > "$UNITS/$TIMER.service" <<UNIT
[Unit]
Description=Netzsperre: Port 80/443 nur für bunny.net (Liste aktualisieren, Regeln setzen)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$BASIS
ExecStart=/bin/sh $BASIS/deploy/cdn-netzsperre.sh aktualisieren
UNIT
  cat > "$UNITS/$TIMER.timer" <<'UNIT'
[Unit]
Description=Netzsperre für bunny.net alle 30 Minuten prüfen

[Timer]
OnBootSec=30s
OnUnitActiveSec=30min

[Install]
WantedBy=timers.target
UNIT
  $SYSTEMCTL daemon-reload
  $SYSTEMCTL enable --now "$TIMER.timer" >/dev/null 2>&1 || $SYSTEMCTL enable --now "$TIMER.timer"
}

vorbedingungen() {
  [ -f "$ENV" ] || { echo "Abbruch: $ENV nicht gefunden – im Installationsordner ausführen." >&2; exit 1; }
  command -v "${NFT%% *}" >/dev/null 2>&1 || { echo "Abbruch: nft fehlt (apt-get install nftables)." >&2; exit 1; }
  schluessel=$(envwert CDN_SCHLUESSEL)
  if [ "$(envwert CDN_PFLICHT)" != 1 ] || ! printf '%s' "$schluessel" | grep -Eq '^[A-Za-z0-9]{32,128}$'; then
    echo "Abbruch: Die Netzsperre setzt voraus, dass alle Adressen über bunny laufen und die Sperre per Schlüssel an ist" >&2
    echo "(CDN_SCHLUESSEL und CDN_PFLICHT=1 in .env, docs/bunny-cdn.md Schritt 7)." >&2
    exit 1
  fi
  schnittstelle >/dev/null || { echo "Abbruch: keine Standardroute gefunden." >&2; exit 1; }
}

case "$BEFEHL" in
  beobachten|an)
    vorbedingungen
    rc=0; py abrufen "$LISTE" || rc=$?
    [ "$rc" != 2 ] || { echo "Abbruch: ohne bunny-Liste wird nichts gesetzt." >&2; exit 1; }
    timer_einrichten
    echo "$BEFEHL" > "$MODUS_DATEI"
    anwenden "$BEFEHL" || { echo "Abbruch: Regeln nicht gesetzt – Modus bleibt gespeichert, der Timer versucht es erneut." >&2; exit 1; }
    if [ "$BEFEHL" = an ]; then
      domain=$(envwert DOMAIN)
      i=0; gut=0
      while [ $i -lt 3 ]; do
        i=$((i + 1))
        if $CURL -fsS -m 15 -o /dev/null "https://$domain/api/?action=status&netzsperre=$(date +%s)"; then gut=1; break; fi
        sleep "$PAUSE"
      done
      if [ "$gut" != 1 ]; then
        echo beobachten > "$MODUS_DATEI"; anwenden beobachten || true
        echo "FEHLER: Probe über bunny (https://$domain/) gescheitert – zurück auf Modus beobachten, nichts wird verworfen." >&2
        exit 1
      fi
      echo "Probe über bunny erfolgreich: https://$domain/ erreicht den Server."
    else
      echo "Nichts wird verworfen. Nach 1–2 Tagen: sh deploy/cdn-netzsperre.sh status, dann sh deploy/cdn-netzsperre.sh an"
    fi
    ;;
  aktualisieren)
    m=$(modus)
    if [ "$m" = aus ]; then entfernen; exit 0; fi
    if py faellig "$LISTE" 6; then py abrufen "$LISTE" || true; fi
    anwenden "$m"
    ;;
  aus)
    entfernen
    $SYSTEMCTL disable --now "$TIMER.timer" >/dev/null 2>&1 || true
    rm -f "$UNITS/$TIMER.service" "$UNITS/$TIMER.timer" "$MODUS_DATEI"
    $SYSTEMCTL daemon-reload >/dev/null 2>&1 || true
    echo "Netzsperre aus: Port 443 nimmt wieder Verbindungen von überall an (Sperre per Schlüssel und Hostinger-Firewall gelten weiter)."
    ;;
  status)
    m=$(modus)
    echo "Netzsperre: $m"
    if tabelle_da; then
      echo "Regeln gesetzt: $(cut -d' ' -f2- "$STAND" 2>/dev/null || echo 'unbekannt')"
      n=$($NFT list table $TABELLE 2>/dev/null | sed -n 's/.*counter packets \([0-9]*\).*/\1/p' | awk '{s += $1} END {print s + 0}')
      if [ "$m" = an ]; then echo "Verworfene fremde Verbindungen seit dem Setzen: $n"; else echo "Gezählte fremde Verbindungen seit dem Setzen: $n"; fi
    else
      echo "Regeln gesetzt: nein"
    fi
    [ "$m" = aus ] || echo "Timer: $($SYSTEMCTL is-active "$TIMER.timer" 2>/dev/null || true)"
    $JOURNAL -k --since "-24h" -o cat --no-pager 2>/dev/null | grep 'stafl-netzsperre:' | py bericht "$LISTE" || true
    ;;
  *)
    echo "Aufruf: sh deploy/cdn-netzsperre.sh status|beobachten|an|aus|aktualisieren" >&2
    exit 2
    ;;
esac
