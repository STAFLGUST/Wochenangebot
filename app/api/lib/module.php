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

/* ---------- Wartung je Oberfläche (GR-107) ----------
   angebot.kunden nutzt weiterhin den bisherigen Wartungsmodus (Dokument „wartung“, Aktion wartung_save) – unverändert,
   damit ein Rückfall auf die Vorversion ihn weiter versteht. Alle anderen Oberflächen: Dokument „module“
   {wartung: {"<modul>.<oberfläche>": {...}}, verlauf: [...]} (ältere Fassungen ignorieren es).
   Eine Wartung mit Beginn in der Zukunft („ab“) ist geplant und wirkt erst ab dann; „bis“ ist nur ein Hinweis –
   beendet wird eine Wartung immer bewusst (kein automatisches Wiederöffnen eines evtl. noch fehlerhaften Bereichs). */
const MODUL_WARTUNG_TEXT = 'Dieser Bereich wird gerade gewartet. Bitte versuchen Sie es später erneut.';
const MODUL_VERLAUF_MAX = 100;

function modul_laufzeit(): array
{
    $d = store_read('module');
    return ['wartung' => is_array($d['wartung'] ?? null) ? $d['wartung'] : [], 'verlauf' => is_array($d['verlauf'] ?? null) ? $d['verlauf'] : []];
}

/* Gespeicherte Wartung einer Oberfläche (auch geplante), sonst null */
function modul_wartung_eintrag(string $modul, string $oberflaeche): ?array
{
    if ($modul === 'angebot' && $oberflaeche === 'kunden') {
        $w = wartung();
        return $w ? ['active' => true, 'message' => $w['message'], 'until' => $w['until'], 'since' => $w['since'], 'by' => $w['by'], 'ab' => null, 'grund' => ''] : null;
    }
    $w = modul_laufzeit()['wartung']["$modul.$oberflaeche"] ?? null;
    return is_array($w) && !empty($w['active']) ? $w : null;
}

/* Wirksame Wartung (aktiv und Beginn erreicht) */
function modul_wartung(string $modul, string $oberflaeche): ?array
{
    $w = modul_wartung_eintrag($modul, $oberflaeche);
    if (!$w) return null;
    if (!empty($w['ab']) && strtotime((string)$w['ab']) > time()) return null;
    return $w;
}

function modul_betrieb(string $modul, string $oberflaeche): string
{
    return modul_wartung($modul, $oberflaeche) ? 'wartung' : 'normal';
}

/* Eintrag in den Verlauf (Dokument „module“) – für alle Oberflächen einschließlich angebot.kunden */
function modul_verlauf_eintragen(array $eintrag): void
{
    with_lock('module', function () use ($eintrag) {
        $d = store_read('module') ?? [];
        $v = is_array($d['verlauf'] ?? null) ? $d['verlauf'] : [];
        array_unshift($v, $eintrag);
        $d['verlauf'] = array_slice($v, 0, MODUL_VERLAUF_MAX);
        if (!is_array($d['wartung'] ?? null)) $d['wartung'] = [];
        store_write('module', $d);
    });
}

function modul_text(string $s, int $max): string
{
    return mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', $s) ?? '')), 0, $max);
}
function modul_zeit(string $s, string $feld): ?string
{
    if ($s === '') return null;
    if (!preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/D', $s) || strtotime($s) === false) throw new InvalidArgumentException("Bitte eine gültige Uhrzeit für „{$feld}“ angeben.");
    return $s;
}

/* Wartung einer Oberfläche setzen oder beenden ($me: bestätigter Administrator). Nur sperrbare, interne, freigegebene
   Oberflächen; das Kunden-Frontend weiter über den bisherigen Wartungsmodus. */
function modul_wartung_setzen(string $ziel, array $b, array $me): ?array
{
    [$modul, $oberflaeche] = array_pad(explode('.', $ziel, 2), 2, '');
    $o = MODULE[$modul]['oberflaechen'][$oberflaeche] ?? null;
    if (!$o) throw new InvalidArgumentException('Unbekannter Bereich.');
    if ($ziel === 'angebot.kunden') throw new InvalidArgumentException('Die Angebotsseite für Kunden bitte über „Wartungsmodus (Angebotsseite)“ steuern.');
    if (!$o['sperrbar']) throw new InvalidArgumentException('Dieser Bereich kann nicht in Wartung gesetzt werden (Schutz vor Aussperrung).');
    if ($o['art'] !== 'intern') throw new InvalidArgumentException('Externe Bereiche werden hier nicht gesteuert.');
    if (!in_array($o['freigabe'], ['produktiv', 'test'], true)) throw new InvalidArgumentException('Dieser Bereich ist noch nicht freigegeben – eine Wartung hätte keine Wirkung.');
    $an = !empty($b['active']);
    $grund = modul_text((string)($b['grund'] ?? ''), 200);
    $msg = modul_text((string)($b['message'] ?? ''), 500);
    $bis = modul_zeit((string)($b['until'] ?? ''), 'voraussichtlich bis');
    $ab = modul_zeit((string)($b['ab'] ?? ''), 'Beginn');
    if ($an && mb_strlen($grund) < 3) throw new InvalidArgumentException('Bitte einen Grund angeben (wird protokolliert).');
    $neuGeplant = $an && $ab !== null && strtotime($ab) > time();
    $alt = null;
    $neu = with_lock('module', function () use ($ziel, $an, $grund, $msg, $bis, $ab, $me, $neuGeplant, &$alt) {
        $d = store_read('module') ?? [];
        $w = is_array($d['wartung'] ?? null) ? $d['wartung'] : [];
        $alt = is_array($w[$ziel] ?? null) && !empty($w[$ziel]['active']) ? $w[$ziel] : null;
        $altLaeuft = $alt && !(!empty($alt['ab']) && strtotime((string)$alt['ab']) > time());
        if ($an) $w[$ziel] = ['active' => true, 'grund' => $grund, 'message' => $msg, 'until' => $bis, 'ab' => $ab,
                              'since' => $altLaeuft && !$neuGeplant ? $alt['since'] : ($neuGeplant ? $ab : now()), 'by' => $me['name'], 'changed' => now()];
        else unset($w[$ziel]);
        $d['wartung'] = $w;
        $v = is_array($d['verlauf'] ?? null) ? $d['verlauf'] : [];
        array_unshift($v, ['t' => now(), 'wer' => $me['name'], 'bereich' => $ziel, 'alt' => $alt ? ($altLaeuft ? 'wartung' : 'wartung geplant') : 'normal',
                           'neu' => $an ? ($neuGeplant ? 'wartung geplant' : 'wartung') : 'normal',
                           'grund' => $grund, 'ab' => $an ? $ab : null, 'bis' => $an ? $bis : null]);
        $d['verlauf'] = array_slice($v, 0, MODUL_VERLAUF_MAX);
        store_write('module', $d);
        return $an ? $w[$ziel] : null;
    });
    $name = MODULE[$modul]['name'] . ' · ' . $o['name'];
    $altLaeuft = $alt && !(!empty($alt['ab']) && strtotime((string)$alt['ab']) > time());
    $text = !$an ? "Wartung beendet: {$name}" : ($neuGeplant ? "Wartung geplant: {$name} ab {$ab}" : ($altLaeuft ? "Wartung geändert: {$name}" : "Wartung gestartet: {$name}"));
    audit('wartung', $text . ($grund !== '' ? " – Grund: {$grund}" : ''), [['k' => 'wartung|' . $ziel, 'code' => '', 'name' => $name, 'f' => 'Wartung',
        'from' => $alt ? 'an' : 'aus', 'to' => $an ? 'an' : 'aus']]);
    return $neu;
}

/* Durchsetzung im API-Einstieg (index.php): Aktionen einer Oberfläche, die für den Nutzer gerade nicht zugänglich ist,
   laufen nicht. Öffentliche Aktionen regelt weiterhin der bisherige Wartungsmodus (kunden_wartung, GR-009);
   „wartung_frei“ (Anmeldung, Abmelden, Status) bleibt erreichbar, damit Administratoren sich anmelden können. */
function modul_durchsetzen(?array $aktion): void
{
    if ($aktion === null || $aktion['oeffentlich'] || $aktion['wartung_frei']) return;
    [$modul, $oberflaeche] = array_pad(explode('.', (string)$aktion['oberflaeche'], 2), 2, '');
    $z = modul_zustand($modul, $oberflaeche, current_user());
    if ($z === null || $z['zugang']) return;
    header('Cache-Control: no-store');
    if ($z['betrieb'] === 'wartung') {
        $w = modul_wartung($modul, $oberflaeche) ?? [];
        header('Retry-After: 600');
        respond(['ok' => false, 'wartung' => true, 'bereich' => "$modul.$oberflaeche", 'error' => ($w['message'] ?? '') !== '' ? $w['message'] : MODUL_WARTUNG_TEXT,
                 'until' => $w['until'] ?? null], 503);
    }
    fail('Dieser Bereich ist nicht verfügbar.', 404);
}

function modul_zustand(string $modul, string $oberflaeche, ?array $u): ?array
{
    $o = MODULE[$modul]['oberflaechen'][$oberflaeche] ?? null;
    if ($o === null) return null;
    $lage = ['entwicklung' => $o['entwicklung'], 'freigabe' => $o['freigabe'], 'betrieb' => modul_betrieb($modul, $oberflaeche), 'person' => modul_person($u)];
    $r = modul_entscheiden($lage);
    return $lage + ['zugang' => $r['zugang'], 'http' => $r['http'], 'kachel' => $r['kachel'], 'hinweis' => $r['hinweis'], 'regel' => $r['nr']];
}

/* Angaben zu einer (auch geplanten) Wartung für die Anzeige; Grund und Urheber nur für Administratoren */
function modul_wartung_anzeige(string $modul, string $oberflaeche, ?array $u): ?array
{
    $w = modul_wartung_eintrag($modul, $oberflaeche);
    if (!$w) return null;
    $out = ['message' => (string)($w['message'] ?? ''), 'until' => $w['until'] ?? null, 'ab' => $w['ab'] ?? null, 'since' => $w['since'] ?? null,
            'geplant' => !empty($w['ab']) && strtotime((string)$w['ab']) > time()];
    if (($u['role'] ?? '') === 'admin') $out += ['grund' => (string)($w['grund'] ?? ''), 'by' => (string)($w['by'] ?? '')];
    return $out;
}

/* Übersicht für das Dashboard und die Modulverwaltung (Aktion module_status, nur angemeldete Mitarbeiter). */
function modul_uebersicht(?array $u): array
{
    $out = [];
    foreach (MODULE as $id => $m) {
        $obs = [];
        foreach ($m['oberflaechen'] as $oid => $o) {
            $obs[] = ['id' => $oid, 'name' => $o['name'], 'art' => $o['art'], 'adresse' => $o['adresse'], 'ziel' => $o['ziel'], 'sperrbar' => $o['sperrbar'],
                      'wartung' => modul_wartung_anzeige($id, $oid, $u)] + modul_zustand($id, $oid, $u);
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
