<?php
declare(strict_types=1);
/* Aktionen: Kundengruppen (Stammdaten → Kundengruppen). Ansehen mit „stammdaten.sehen“ oder „kunden.sehen“,
   Ändern und CSV-Import mit „stammdaten.bearbeiten“. Kunden verweisen über „gruppe“ auf die Nummer.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'kundengruppen': {
            $me = require_auth();
            if (!may($me, 'stammdaten.sehen') && !may($me, 'kunden.sehen')) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            header('Cache-Control: no-store');
            $d = kundengruppen_load();
            $out = ['ok' => true, 'rev' => $d['rev'], 'groups' => $d['groups'], 'updatedAt' => $d['updatedAt'], 'updatedBy' => $d['updatedBy']];
            if (may($me, 'kunden.sehen')) {   // Anzahl zugeordneter Kunden nur für Berechtigte
                $n = [];
                foreach (customers_load()['customers'] as $c) if (($c['gruppe'] ?? '') !== '') $n[$c['gruppe']] = ($n[$c['gruppe']] ?? 0) + 1;
                $out['kunden'] = (object)$n;
            }
            respond($out);
        }

        case 'kundengruppen_save': {
            $me = require_perm('stammdaten.bearbeiten', true);
            $b = body();
            $groups = kundengruppen_clean($b['groups'] ?? null);
            $quelle = s($b['quelle'] ?? '', 120) ?? '';
            $res = with_lock('kundengruppen', function () use ($b, $groups, $me) {
                $cur = kundengruppen_load();
                if ((int)($b['rev'] ?? -1) !== $cur['rev']) fail('Die Kundengruppen wurden inzwischen an anderer Stelle geändert. Bitte neu laden.', 409);
                $alt = []; foreach ($cur['groups'] as $g) $alt[$g['nr']] = $g;
                $neu = 0; $geaendert = 0;
                foreach ($groups as $g) { if (!isset($alt[$g['nr']])) $neu++; elseif ($alt[$g['nr']] != $g) $geaendert++; unset($alt[$g['nr']]); }
                $d = ['rev' => $cur['rev'] + 1, 'groups' => $groups, 'updatedAt' => now(), 'updatedBy' => $me['name']];
                store_write('kundengruppen', $d);
                return [$d, $neu, $geaendert, count($alt)];
            });
            [$d, $neu, $geaendert, $weg] = $res;
            if ($neu || $geaendert || $weg) audit('master', 'Kundengruppen ' . ($quelle !== '' ? "aus „{$quelle}“ übernommen" : 'gespeichert') . ": $neu neu, $geaendert geändert, $weg entfernt (" . count($groups) . ' insgesamt)');
            respond(['ok' => true, 'rev' => $d['rev'], 'groups' => $d['groups'], 'neu' => $neu, 'geaendert' => $geaendert, 'entfernt' => $weg]);
        }
}
