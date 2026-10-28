# Testauszug der Detailkarte

`hamburg.pmtiles` – kleiner Ausschnitt der Protomaps-Basiskarte für die Keycloak-Testumgebung (`tests/oidc/`):
Deutschland grob (Zoomstufen 0–5) und ein Teil der Hamburger Innenstadt bis Zoomstufe 15 (Straßen, Gebäude).
Im Betrieb lädt `deploy/karte-laden.sh` den ganzen Ausschnitt Deutschland.

Daten: © OpenStreetMap-Mitwirkende, Open Database License (ODbL) – https://www.openstreetmap.org/copyright ·
Kachelung: Protomaps (https://protomaps.com). Keine Geschäftsdaten.

Erzeugt mit:

```sh
python3 werkzeuge/karte_auszug.py https://build.protomaps.com/20261026.pmtiles tests/fixtures/karte/hamburg.pmtiles \
    --bereich 5.5,47.2,15.5,55.1:0-5 --bereich 9.988,53.548,9.998,53.553:6-15
```
