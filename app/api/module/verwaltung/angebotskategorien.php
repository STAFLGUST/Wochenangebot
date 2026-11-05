<?php
declare(strict_types=1);
/* Angebotskategorien (Stammdaten der Verwaltung, Wunsch des Inhabers vom 05.11.2026).
   Eine Angebotskategorie ist ein Abschnitt des Angebots (z. B. „Eigene Zerlegung, Marke „Fleischmeister““). Ihr sind
   VK-Gruppen der Warenwirtschaft zugeordnet – in fester Reihenfolge, jede VK-Gruppe höchstens einer Kategorie. Die
   Reihenfolge der Kategorien und darin der VK-Gruppen bestimmt den Aufbau aller Angebote (der Editor ordnet den Entwurf
   danach, OfferCore.nachKategorien). Ohne Kategorien bleibt das Angebot wie von Hand geordnet.

   Dokument „angebotskategorien“: { rev, kategorien: [{ id, name, vk: ["1150", …] }], updatedAt, updatedBy }
   Lesen: stammdaten.sehen oder angebot.bearbeiten (der Editor braucht die Ordnung); Ändern: stammdaten.bearbeiten.
   Eingebunden von aktionen/kundengruppen.php; Speicherzugriffe nur auf das eigene Dokument und lesend auf „vkgruppen“. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const KATEGORIEN_MAX = 100, KATEGORIEN_VK_MAX = 1000;

function kategorien_load(): array
{
    $d = store_read('angebotskategorien');
    return ['rev' => (int)($d['rev'] ?? 0), 'kategorien' => is_array($d['kategorien'] ?? null) ? array_values($d['kategorien']) : [],
            'updatedAt' => $d['updatedAt'] ?? null, 'updatedBy' => (string)($d['updatedBy'] ?? '')];
}

/* Gesendete Liste prüfen und vereinheitlichen. Fehler: InvalidArgumentException (→ 422) mit verständlicher Meldung. */
function kategorien_clean($liste): array
{
    if (!is_array($liste) || !array_is_list($liste)) throw new InvalidArgumentException('Die Angebotskategorien fehlen.');
    if (count($liste) > KATEGORIEN_MAX) throw new InvalidArgumentException('Höchstens ' . KATEGORIEN_MAX . ' Angebotskategorien.');
    $out = []; $ids = []; $namen = []; $vkBei = [];
    foreach ($liste as $k) {
        if (!is_array($k)) throw new InvalidArgumentException('Ungültige Angebotskategorie.');
        $name = s($k['name'] ?? null, 200, false);
        if ($name === null || $name === '') throw new InvalidArgumentException('Jede Angebotskategorie braucht eine Bezeichnung.');
        $key = mb_strtolower($name);
        if (isset($namen[$key])) throw new InvalidArgumentException("Die Angebotskategorie „{$name}“ gibt es doppelt.");
        $namen[$key] = true;
        $id = s($k['id'] ?? '', 40) ?? '';
        if ($id === '' || !preg_match('/^[A-Za-z0-9_-]{1,40}$/', $id) || isset($ids[$id])) $id = 'k' . bin2hex(random_bytes(5));
        $ids[$id] = true;
        $vk = [];
        foreach (is_array($k['vk'] ?? null) ? array_values($k['vk']) : [] as $v) {
            $v = is_int($v) ? (string)$v : (is_string($v) ? trim($v) : '');
            if (!preg_match('/^[0-9A-Za-z._-]{1,10}$/', $v)) throw new InvalidArgumentException('Ungültige VK-Gruppe in „' . $name . '“.');
            if (isset($vkBei[$v])) throw new InvalidArgumentException("Die VK-Gruppe {$v} steht in „{$vkBei[$v]}“ und in „{$name}“ – jede VK-Gruppe gehört zu höchstens einer Kategorie.");
            $vkBei[$v] = $name;
            $vk[] = $v;
        }
        if (count($vk) > KATEGORIEN_VK_MAX) throw new InvalidArgumentException('Zu viele VK-Gruppen in „' . $name . '“.');
        $out[] = ['id' => $id, 'name' => $name, 'vk' => $vk];
    }
    return $out;
}

/* Speichern mit Revision (409 bei zwischenzeitlicher Änderung) und Protokoll. Weitere Felder einer neueren Fassung bleiben (GR-006). */
function kategorien_speichern($liste, int $rev, array $me): array
{
    $neu = kategorien_clean($liste);
    $d = with_lock('angebotskategorien', function () use ($neu, $rev, $me) {
        $cur = kategorien_load();
        if ($rev !== $cur['rev']) fail('Die Angebotskategorien wurden inzwischen an anderer Stelle geändert. Bitte neu laden.', 409);
        $roh = store_read('angebotskategorien');
        $d = ['rev' => $cur['rev'] + 1, 'kategorien' => $neu, 'updatedAt' => now(), 'updatedBy' => $me['name']] + (is_array($roh) ? $roh : []);
        store_write('angebotskategorien', $d);
        return [$d, $cur['kategorien']];
    });
    [$doc, $alt] = $d;
    $zuordnungen = array_sum(array_map(fn($k) => count($k['vk']), $neu));
    if ($alt != $neu) audit('master', 'Angebotskategorien gespeichert: ' . count($neu) . ' Kategorien, ' . $zuordnungen . ' VK-Gruppen zugeordnet (vorher ' . count($alt) . ' Kategorien)');
    return ['rev' => $doc['rev'], 'kategorien' => $doc['kategorien'], 'updatedAt' => $doc['updatedAt'], 'updatedBy' => $doc['updatedBy']];
}

/* Nummer und Bezeichnung der VK-Gruppen – für Ansicht und Editor (auch ohne „stammdaten.sehen“, nur diese zwei Felder) */
function kategorien_vk_namen(): array
{
    $out = [];
    foreach (gruppen_load('vkgruppen')['groups'] as $g) if (isset($g['nr'])) $out[] = ['nr' => (string)$g['nr'], 'name' => (string)($g['name'] ?? '')];
    return $out;
}
