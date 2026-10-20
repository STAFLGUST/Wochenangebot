<?php
declare(strict_types=1);
/* Aktionen: Gruppenlisten der Stammdaten – Kundengruppen und VK-Gruppen (Beschreibung: lib/kunden.php).
   Kundengruppen ansehen mit „stammdaten.sehen“ oder „kunden.sehen“, VK-Gruppen mit „stammdaten.sehen“;
   Ändern und CSV-Import mit „stammdaten.bearbeiten“. Kunden verweisen über „gruppe“, Artikel über „vkGruppe“ auf die Nummer.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'kundengruppen':
        case 'vkgruppen': {
            $me = require_auth();
            $vk = $action === 'vkgruppen';
            if (!may($me, 'stammdaten.sehen') && ($vk || !may($me, 'kunden.sehen'))) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            header('Cache-Control: no-store');
            $d = gruppen_load($action);
            $out = ['ok' => true, 'rev' => $d['rev'], 'groups' => $d['groups'], 'updatedAt' => $d['updatedAt'], 'updatedBy' => $d['updatedBy']];
            $n = [];
            if ($vk) {   // Anzahl zugeordneter Artikel (Stammdaten)
                foreach ((store_read('stammdaten')['articles'] ?? []) as $a) if (($a['vkGruppe'] ?? '') !== '') $n[$a['vkGruppe']] = ($n[$a['vkGruppe']] ?? 0) + 1;
                $out['artikel'] = (object)$n;
            } elseif (may($me, 'kunden.sehen')) {   // Anzahl zugeordneter Kunden nur für Berechtigte
                foreach (customers_load()['customers'] as $c) if (($c['gruppe'] ?? '') !== '') $n[$c['gruppe']] = ($n[$c['gruppe']] ?? 0) + 1;
                $out['kunden'] = (object)$n;
            }
            respond($out);
        }

        case 'kundengruppen_save':
        case 'vkgruppen_save': {
            $me = require_perm('stammdaten.bearbeiten', true);
            $liste = $action === 'vkgruppen_save' ? 'vkgruppen' : 'kundengruppen';
            $L = GRUPPEN_LISTEN[$liste];
            $b = body();
            $groups = gruppen_clean($liste, $b['groups'] ?? null);
            $quelle = s($b['quelle'] ?? '', 120) ?? '';
            $res = with_lock($liste, function () use ($b, $groups, $me, $liste, $L) {
                $cur = gruppen_load($liste);
                if ((int)($b['rev'] ?? -1) !== $cur['rev']) fail("Die {$L['viele']} wurden inzwischen an anderer Stelle geändert. Bitte neu laden.", 409);
                $alt = []; foreach ($cur['groups'] as $g) $alt[$g['nr']] = $g;
                $neu = 0; $geaendert = 0;
                foreach ($groups as $g) { if (!isset($alt[$g['nr']])) $neu++; elseif ($alt[$g['nr']] != $g) $geaendert++; unset($alt[$g['nr']]); }
                $d = ['rev' => $cur['rev'] + 1, 'groups' => $groups, 'updatedAt' => now(), 'updatedBy' => $me['name']];
                store_write($liste, $d);
                return [$d, $neu, $geaendert, count($alt)];
            });
            [$d, $neu, $geaendert, $weg] = $res;
            if ($neu || $geaendert || $weg) audit('master', $L['viele'] . ' ' . ($quelle !== '' ? "aus „{$quelle}“ übernommen" : 'gespeichert') . ": $neu neu, $geaendert geändert, $weg entfernt (" . count($groups) . ' insgesamt)');
            respond(['ok' => true, 'rev' => $d['rev'], 'groups' => $d['groups'], 'neu' => $neu, 'geaendert' => $geaendert, 'entfernt' => $weg]);
        }
}
