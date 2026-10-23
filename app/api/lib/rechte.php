<?php
declare(strict_types=1);
/* Nutzerrechte: was eine Rolle bzw. ein einzelner Nutzer im Eingabebereich sehen und tun darf.
   Administratoren haben immer alle Rechte; Nutzer, Rechte, Sicherheit und E-Mail-Einstellungen bleiben fest
   den Administratoren vorbehalten (sonst könnte sich jemand selbst höhere Rechte geben).
   Gespeichert: Dokument „rechte“ (Rechte je Rolle) und je Nutzer „grant“/„deny“ (Ausnahmen). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Schlüssel => Bereich, Bezeichnung, Art (sehen|machen), Standard-Rollen, setzt voraus.
   Die Standards entsprechen dem bisherigen festen Rollenmodell. */
const PERMS = [
    'angebot.bearbeiten'       => ['g' => 'Angebot', 'l' => 'Entwurf bearbeiten (Preise, Artikel, Excel-Import, frühere Version laden)', 'k' => 'machen', 'd' => ['editor'], 'r' => []],
    'angebot.veroeffentlichen' => ['g' => 'Angebot', 'l' => 'Angebot veröffentlichen', 'k' => 'machen', 'd' => ['editor'], 'r' => []],
    'angebote.verwalten'       => ['g' => 'Angebot', 'l' => 'Kundenangebote anlegen und umbenennen', 'k' => 'machen', 'd' => ['editor'], 'r' => []],
    'angebote.loeschen'        => ['g' => 'Angebot', 'l' => 'Kundenangebote löschen, Wochenangebot nur für Kunden sichtbar machen', 'k' => 'machen', 'd' => [], 'r' => ['angebote.verwalten']],
    'preisverlauf.sehen'       => ['g' => 'Preisverlauf', 'l' => 'Preisverlauf ansehen', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => []],
    'preisverlauf.bearbeiten'  => ['g' => 'Preisverlauf', 'l' => 'Alte Angebotslisten hochladen und löschen', 'k' => 'machen', 'd' => ['editor'], 'r' => ['preisverlauf.sehen']],
    'bestand.sehen'            => ['g' => 'Bestand', 'l' => 'Bestand mit Mengen und MHD ansehen', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => []],
    'bestand.einkaufspreise'   => ['g' => 'Bestand', 'l' => 'Einkaufspreise (EK) der Partien im Bestand ansehen', 'k' => 'sehen', 'd' => ['editor'], 'r' => ['bestand.sehen']],
    'bestand.importieren'      => ['g' => 'Bestand', 'l' => 'Bestandsliste hochladen', 'k' => 'machen', 'd' => ['editor'], 'r' => ['bestand.sehen']],
    'stammdaten.sehen'         => ['g' => 'Stammdaten', 'l' => 'Stammdaten ansehen', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => []],
    'stammdaten.bearbeiten'    => ['g' => 'Stammdaten', 'l' => 'Stammdaten bearbeiten', 'k' => 'machen', 'd' => ['editor'], 'r' => ['stammdaten.sehen']],
    'einkauf.sehen'            => ['g' => 'Einkauf', 'l' => 'Einkauf (Fehlmengen) ansehen', 'k' => 'sehen', 'd' => ['viewer', 'editor'], 'r' => []],
    'einkauf.melden'           => ['g' => 'Einkauf', 'l' => 'Einkauf per E-Mail benachrichtigen', 'k' => 'machen', 'd' => ['editor'], 'r' => ['einkauf.sehen']],
    'hr.antrag'                => ['g' => 'HR', 'l' => 'Eigenen Urlaub beantragen, Abwesenheitskalender ansehen (nur „abwesend“)', 'k' => 'machen', 'd' => ['viewer', 'editor'], 'r' => []],
    'hr.verwalten'             => ['g' => 'HR', 'l' => 'Personalstelle: Urlaub genehmigen, Abwesenheiten mit Grund, Mitarbeiter, Excel-Export', 'k' => 'machen', 'd' => [], 'r' => ['hr.antrag']],
    'crm.sehen'                => ['g' => 'CRM', 'l' => 'CRM ansehen: Kunden mit Ansprechpartnern, Wiedervorlagen, Pipeline, Aktivitäten, Auswertung', 'k' => 'sehen', 'd' => [], 'r' => []],
    'crm.bearbeiten'           => ['g' => 'CRM', 'l' => 'CRM bearbeiten: Kundenblätter, Ansprechpartner, Interessenten, Aktivitäten erfassen', 'k' => 'machen', 'd' => [], 'r' => ['crm.sehen']],
    'crm.exportieren'          => ['g' => 'CRM', 'l' => 'CRM-Liste mit Kontaktdaten als CSV herunterladen', 'k' => 'machen', 'd' => [], 'r' => ['crm.sehen']],
    'bestellungen.sehen'       => ['g' => 'Bestellungen', 'l' => 'Bestellwünsche mit Kundendaten ansehen', 'k' => 'sehen', 'd' => ['editor'], 'r' => []],
    'bestellungen.bearbeiten'  => ['g' => 'Bestellungen', 'l' => 'Bestellwünsche bearbeiten (Status, Notiz, E-Mail erneut senden)', 'k' => 'machen', 'd' => ['editor'], 'r' => ['bestellungen.sehen']],
    'kunden.sehen'             => ['g' => 'Kunden', 'l' => 'Kundenstammdaten ansehen', 'k' => 'sehen', 'd' => [], 'r' => []],
    'einzelangebote.sehen'     => ['g' => 'Kunden', 'l' => 'Einzelangebote für Kunden ansehen', 'k' => 'sehen', 'd' => [], 'r' => ['kunden.sehen']],
    'einzelangebote.bearbeiten' => ['g' => 'Kunden', 'l' => 'Einzelangebote erstellen, im Portal freigeben und per E-Mail senden', 'k' => 'machen', 'd' => [], 'r' => ['einzelangebote.sehen']],
    'kunden.bearbeiten'        => ['g' => 'Kunden', 'l' => 'Kunden anlegen, ändern, löschen, Zugänge und Einladungen', 'k' => 'machen', 'd' => [], 'r' => ['kunden.sehen']],
    'wochenangebot.senden'     => ['g' => 'Kunden', 'l' => 'Wochenangebot per E-Mail an Kunden senden', 'k' => 'machen', 'd' => [], 'r' => ['kunden.sehen']],
    'sonderposten.senden'      => ['g' => 'Kunden', 'l' => 'Sonderposten per E-Mail an Kunden senden', 'k' => 'machen', 'd' => [], 'r' => ['kunden.sehen']],
    'protokoll.sehen'          => ['g' => 'Verwaltung', 'l' => 'Protokoll ansehen', 'k' => 'sehen', 'd' => [], 'r' => []],
    'auswertung.sehen'         => ['g' => 'Verwaltung', 'l' => 'Auswertung: Karte der Kunden-Anmeldungen ansehen', 'k' => 'sehen', 'd' => [], 'r' => ['kunden.sehen']],
];
/* Fest den Administratoren vorbehalten (nur zur Anzeige in der Rechte-Übersicht) */
const PERMS_ADMIN_ONLY = ['Mitarbeiter (Anmeldung) und Rechte verwalten', 'Sicherheit und Wartungsmodus', 'E-Mail-Postfach, Signatur und Benachrichtigungen'];
const PERM_ROLES = ['viewer', 'editor'];

/* Rechte je Rolle (gespeichert oder Standard) */
function rights_roles(): array
{
    $d = store_read('rechte');
    $out = [];
    foreach (PERM_ROLES as $r) {
        if (is_array($d['roles'][$r] ?? null)) $out[$r] = array_values(array_intersect(array_keys(PERMS), $d['roles'][$r]));
        else $out[$r] = array_keys(array_filter(PERMS, function ($p) use ($r) { return in_array($r, $p['d'], true); }));
    }
    return $out;
}
function rights_clean(array $list): array { return array_values(array_unique(array_intersect(array_keys(PERMS), array_map('strval', $list)))); }
/* Voraussetzungen ergänzen (wer bearbeiten darf, darf auch sehen) */
function rights_close(array $perms): array
{
    $set = array_flip($perms);
    do {
        $added = false;
        foreach (array_keys($set) as $p) foreach (PERMS[$p]['r'] ?? [] as $req) if (!isset($set[$req])) { $set[$req] = true; $added = true; }
    } while ($added);
    return array_values(array_intersect(array_keys(PERMS), array_keys($set)));
}
/* Wirksame Rechte eines Nutzers: Rolle + erlaubt − verboten (Administrator: alle) */
function user_perms(array $u, ?array $roles = null): array
{
    if (($u['role'] ?? '') === 'admin') return array_keys(PERMS);
    $roles = $roles ?? rights_roles();
    $p = $roles[$u['role']] ?? [];
    $p = array_merge($p, rights_clean((array)($u['grant'] ?? [])));
    $p = rights_close(array_values(array_unique($p)));
    $deny = rights_clean((array)($u['deny'] ?? []));
    // Verbotenes entfernen, dann alles, dessen Voraussetzung jetzt fehlt
    $p = array_values(array_diff($p, $deny));
    do {
        $n = count($p);
        $p = array_values(array_filter($p, function ($k) use ($p) { foreach (PERMS[$k]['r'] as $req) if (!in_array($req, $p, true)) return false; return true; }));
    } while (count($p) !== $n);
    return $p;
}
function may(array $u, string $perm): bool { return in_array($perm, user_perms($u), true); }
function require_perm(string $perm, bool $write = false): array
{
    $u = require_auth($write);
    if (!may($u, $perm)) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
    return $u;
}
/* Wie require_admin_confirmation, aber für ein Recht statt der Administratorrolle.
   $key: Aktion im Katalog BESTAETIGUNG – ist die Bestätigung dort abgeschaltet, genügen Anmeldung und Recht. */
function require_perm_confirmed(string $perm, string $key = ''): array
{
    if ($key !== '' && !bestaetigung_noetig($key)) return require_perm($perm, true);
    $u = require_perm($perm, true);
    confirmation_locked($u);
    $at = (int)($_SESSION['adminConfirmedAt'] ?? 0);
    if ($at <= time() && $at > time() - bestaetigung_sekunden() && (int)($_SESSION['adminConfirmedSv'] ?? -1) === (int)$u['sv']) return $u;
    respond(['ok' => false, 'code' => 'confirmation_required', 'error' => 'Bitte bestätigen Sie diese Aktion mit Ihrem aktuellen Passwort.'], 403);
}
function rights_catalog(): array
{
    $out = [];
    foreach (PERMS as $k => $p) $out[] = ['key' => $k, 'group' => $p['g'], 'label' => $p['l'], 'kind' => $p['k'], 'requires' => $p['r'], 'default' => $p['d']];
    return $out;
}
