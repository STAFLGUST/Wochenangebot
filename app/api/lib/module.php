<?php
declare(strict_types=1);
/* Modulzustand zur Laufzeit: wer darf welche Oberfläche nutzen (GR-102)?
   Grundlage ist ausschließlich die erzeugte Liste lib/module-liste.php (Modulregister regeln/module.toml und
   Entscheidungstabelle regeln/wartung.toml). Hier wird die Tabelle nur ausgewertet – die Regeln selbst stehen nirgends
   sonst im Code. Vertragstests: tests/regeln/test_regeln.py (PHP ergibt für alle Kombinationen dasselbe wie die Prüfung
   in werkzeuge/regeln.py) und die E2E-Gruppe module_status.
   Der Zugang zu einer Oberfläche ist keine Berechtigung: jede Aktion prüft ihre Rechte weiterhin selbst (GR-103). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

function modul_freigabe_zulaessig(string $entwicklung, string $freigabe): bool
{
    return in_array($freigabe, MODUL_FREIGABE_ERLAUBT[$entwicklung] ?? [], true);
}

/* Erste passende Zeile der Entscheidungstabelle. $lage: entwicklung, freigabe, betrieb, person. */
function modul_entscheiden(array $lage): array
{
    foreach (MODUL_REGELN as $r) {
        $passt = true;
        foreach ($r['wenn'] as $feld => $wert) {
            if ($feld === 'freigabe_unzulaessig') {
                $passt = $wert === !modul_freigabe_zulaessig((string)($lage['entwicklung'] ?? ''), (string)($lage['freigabe'] ?? ''));
            } else {
                $passt = ($lage[$feld] ?? null) === $wert;
            }
            if (!$passt) break;
        }
        if ($passt) return $r;
    }
    // Die CI stellt sicher, dass die Tabelle vollständig ist; fehlt dennoch eine Zeile: sicher sperren
    return ['nr' => 0, 'wenn' => [], 'zugang' => false, 'http' => 404, 'kachel' => 'nicht_verfuegbar', 'hinweis' => false];
}

/* Rolle für die Tabelle: Administratoren dürfen in der Wartung prüfen. Tester je Oberfläche folgen mit der
   Modulverwaltung (Roadmap PR 4/5); bis dahin gibt es keine Testfreigaben. */
function modul_person(?array $u): string
{
    return ($u['role'] ?? '') === 'admin' ? 'administrator' : 'normal';
}

/* Betriebszustand einer Oberfläche. Heute gibt es nur den bisherigen Wartungsmodus der Angebotsseite
   (Dokument „wartung“); er entspricht „angebot.kunden in Wartung“. Wartung je Oberfläche folgt (Roadmap PR 4). */
function modul_betrieb(string $modul, string $oberflaeche): string
{
    if ($modul === 'angebot' && $oberflaeche === 'kunden') return wartung() ? 'wartung' : 'normal';
    return 'normal';
}

function modul_zustand(string $modul, string $oberflaeche, ?array $u): ?array
{
    $o = MODULE[$modul]['oberflaechen'][$oberflaeche] ?? null;
    if ($o === null) return null;
    $lage = ['entwicklung' => $o['entwicklung'], 'freigabe' => $o['freigabe'], 'betrieb' => modul_betrieb($modul, $oberflaeche), 'person' => modul_person($u)];
    $r = modul_entscheiden($lage);
    return $lage + ['zugang' => $r['zugang'], 'http' => $r['http'], 'kachel' => $r['kachel'], 'hinweis' => $r['hinweis'], 'regel' => $r['nr']];
}

/* Übersicht für das Dashboard und die Modulverwaltung (Aktion module_status, nur angemeldete Mitarbeiter). */
function modul_uebersicht(?array $u): array
{
    $out = [];
    foreach (MODULE as $id => $m) {
        $obs = [];
        foreach ($m['oberflaechen'] as $oid => $o) {
            $obs[] = ['id' => $oid, 'name' => $o['name'], 'art' => $o['art'], 'adresse' => $o['adresse'], 'ziel' => $o['ziel']] + modul_zustand($id, $oid, $u);
        }
        $kachel = null;
        if ($m['dashboard'] && $m['kachel_ziel']) {
            [$zm, $zo] = explode('.', $m['kachel_ziel'], 2);
            $z = modul_zustand($zm, $zo, $u);
            $kachel = ['ziel' => $m['kachel_ziel'], 'adresse' => MODULE[$zm]['oberflaechen'][$zo]['adresse'] ?? null,
                       'status' => $z['kachel'] ?? 'nicht_verfuegbar', 'zugang' => (bool)($z['zugang'] ?? false), 'hinweis' => (bool)($z['hinweis'] ?? false)];
        }
        $out[] = ['id' => $id, 'name' => $m['name'], 'beschreibung' => $m['beschreibung'], 'icon' => $m['icon'], 'reihenfolge' => $m['reihenfolge'],
                  'dashboard' => $m['dashboard'], 'teil_von' => $m['teil_von'], 'kachel' => $kachel, 'oberflaechen' => $obs];
    }
    return $out;
}
