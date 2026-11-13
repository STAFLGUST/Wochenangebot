# STAFL-Plattform – Anwendungs-Image (Roadmap 7b-4, ADR-003)
#
# Grundlage für die spätere zentrale Anmeldung: das offizielle PHP-/Apache-Image plus das Apache-Modul mod_auth_openidc
# (OpenID-zertifiziert, aus den Debian-Paketquellen). Das Modul wird hier NUR installiert, nicht geladen – ohne eigene
# Konfiguration verhält sich das Image genau wie php:8.3-apache (in der CI geprüft).
#
# Noch NICHT im Betrieb: docker-compose.yml nutzt weiterhin php:8.3-apache. Die Umstellung des Servers ist ein eigener
# Schritt mit Freigabe des Inhabers.
#
# Grundimage fest über den Digest (Mehrplattform-Index) – neue Digests trägt der wöchentliche Lauf „Sicherheitsupdates“
# per Pull Request ein (werkzeuge/images_aktualisieren.py, überall gleich); CI (Bau, Vergleich mit dem Grundimage,
# Schwachstellen-Scan) muss grün sein.
FROM php:8.3-apache@sha256:a800bbd2c0aa322702259ed475556b2cbc311076a8d3c4bba9bfe96838745472

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends libapache2-mod-auth-openidc; \
    # Sicherheitskorrekturen aus den Debian-Quellen, die das festgelegte Grundimage noch nicht enthält
    # (libbrotli1: CVE-2026-111497, behoben in 1.1.0-2+deb13u1; linux-libc-dev – Kernel-Kopfdateien, im Grundimage für
    # docker-php-ext-install: CVE-2026-99083, behoben in 6.12.115-2; apache2 mit apache2-bin, apache2-data und
    # apache2-utils: CVE-2026-119618 in mod_http2, behoben in 2.4.71-1~deb13u1) – entfällt mit dem nächsten Digest
    # des Grundimages
    apt-get install -y --no-install-recommends --only-upgrade libbrotli1 linux-libc-dev \
        apache2 apache2-bin apache2-data apache2-utils; \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libbrotli1)" ge 1.1.0-2+deb13u1; \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' linux-libc-dev)" ge 6.12.115-2; \
    for paket in apache2 apache2-bin apache2-data apache2-utils; do \
        dpkg --compare-versions "$(dpkg-query -W -f='${Version}' "$paket")" ge 2.4.71-1~deb13u1; \
    done; \
    rm -rf /var/lib/apt/lists/*; \
    # nicht aktivieren: geladen wird das Modul erst durch die Konfiguration eines Keycloak-Hosts
    rm -f /etc/apache2/mods-enabled/auth_openidc.load /etc/apache2/mods-enabled/auth_openidc.conf; \
    test -f /usr/lib/apache2/modules/mod_auth_openidc.so

LABEL org.opencontainers.image.title="stafl-app" \
      org.opencontainers.image.description="PHP 8.3 + Apache + mod_auth_openidc (nicht geladen) für die STAFL-Plattform" \
      org.opencontainers.image.source="https://github.com/STAFLGUST/Wochenangebot"
