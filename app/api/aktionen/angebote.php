<?php
declare(strict_types=1);
/* Aktionen: Angebote (öffentlich und Eingabebereich)
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'offer': {
            header('Cache-Control: no-cache');
            $oid = (string)($_GET['angebot'] ?? OFFER_STD);
            if ($oid === '') $oid = OFFER_STD;
            if (!preg_match('/^[a-z0-9-]{1,40}$/', $oid)) fail('Unbekanntes Angebot.', 404);
            if ($oid !== OFFER_STD || !std_public()) {
                // Mitarbeiter sehen alle Angebote; Kunden nur freigeschaltete; sonst Anmeldung nötig
                if (current_user()) require_auth();
                elseif ($k = current_customer()) {
                    if (!empty($k['login']['mustChange'])) fail('Bitte zuerst ein eigenes Passwort festlegen.', 403);
                    if (!in_array($oid, customer_offers($k), true)) fail('Dieses Angebot ist für Ihren Zugang nicht freigeschaltet.', 403);
                } else fail('Bitte anmelden.', 401);
                header('Cache-Control: private, no-store');
            }
            $def = offer_def($oid);
            if (!$def) fail('Unbekanntes Angebot.', 404);
            if (!empty($_GET['draft'])) {
                require_auth();
                $d = store_read('entwurf') ?? store_read('angebot');
                if (!$d) fail('Kein Entwurf vorhanden.', 404);
                respond(['ok' => true, 'company' => $CFG['company'], 'preview' => true, 'offer' => offer_resolve($d, $def)]);
            }
            $published = store_read('angebot');
            if ($published === null) fail('Es ist noch kein Angebot veröffentlicht.', 404);
            if ($oid === OFFER_STD && std_public()) {
                $etag = '"' . hash('sha256', json_encode($published) . ':std') . '"';
                header('ETag: ' . $etag);
                if (trim((string)($_SERVER['HTTP_IF_NONE_MATCH'] ?? '')) === $etag) { http_response_code(304); exit; }
            }
            respond(['ok' => true, 'company' => $CFG['company'], 'offer' => offer_resolve($published, $def)]);
        }

        case 'offers': {
            require_auth();
            header('Cache-Control: no-store');
            $d = offers_load();
            respond(['ok' => true, 'rev' => $d['rev'], 'offers' => $d['offers'], 'std' => offer_def(OFFER_STD), 'stdPublic' => std_public()]);
        }

        case 'offers_save': {
            $me = require_perm('angebote.verwalten', true);
            $b = body();
            $list = [];
            $names = [];
            foreach (array_slice(is_array($b['offers'] ?? null) ? $b['offers'] : [], 0, 30) as $o) {
                if (!is_array($o)) continue;
                $name = s($o['name'] ?? null, 80, false);
                if ($name === null || mb_strlen($name) < 2) throw new InvalidArgumentException('Jedes Angebot braucht einen Namen (mindestens 2 Zeichen).');
                $key = mb_strtolower($name);
                if (isset($names[$key]) || $key === 'wochenangebot') throw new InvalidArgumentException("Der Name „{$name}“ ist bereits vergeben.");
                $names[$key] = true;
                $id = (string)($o['id'] ?? '');
                if ($id === '' || $id === OFFER_STD || !preg_match('/^[a-z0-9-]{1,40}$/', $id)) throw new InvalidArgumentException('Ungültige Angebots-ID.');
                $fb = ($o['fallback'] ?? '') === 'hidden' ? 'hidden' : 'standard';
                $list[] = ['id' => $id, 'name' => $name, 'fallback' => $fb];
            }
            if (count(array_unique(array_column($list, 'id'))) !== count($list)) throw new InvalidArgumentException('Angebots-IDs sind doppelt.');
            $res = with_lock('angebote', function () use ($b, $list, $me) {
                $cur = offers_load();
                if ((int)($b['rev'] ?? -1) !== (int)$cur['rev']) fail('Die Angebote wurden inzwischen an anderer Stelle geändert. Bitte die Seite neu laden.', 409);
                $old = []; foreach ($cur['offers'] as $o) $old[$o['id']] = $o;
                $new = []; foreach ($list as $o) $new[$o['id']] = $o;
                $removed = array_diff_key($old, $new);
                if ($removed) require_perm_confirmed('angebote.loeschen');
                $d = [];
                $FB = ['standard' => 'Standardpreis zeigen', 'hidden' => 'Artikel ausblenden'];
                foreach ($new as $id => $o) {
                    if (!isset($old[$id])) { $d[] = ['k' => "o$id|+", 'code' => '', 'name' => $o['name'], 'f' => 'Neues Angebot', 'from' => '', 'to' => 'ohne eigenen Preis: ' . $FB[$o['fallback']]]; continue; }
                    if ($old[$id]['name'] !== $o['name']) $d[] = ['k' => "o$id|name", 'code' => '', 'name' => $o['name'], 'f' => 'Name', 'from' => $old[$id]['name'], 'to' => $o['name']];
                    if (($old[$id]['fallback'] ?? 'standard') !== $o['fallback']) $d[] = ['k' => "o$id|fb", 'code' => '', 'name' => $o['name'], 'f' => 'Ohne eigenen Preis', 'from' => $FB[$old[$id]['fallback'] ?? 'standard'], 'to' => $FB[$o['fallback']]];
                }
                foreach ($removed as $id => $o) $d[] = ['k' => "o$id|-", 'code' => '', 'name' => $o['name'], 'f' => 'Angebot gelöscht', 'from' => $o['name'], 'to' => ''];
                $oldPub = !array_key_exists('stdPublic', $cur) || !empty($cur['stdPublic']);
                $pub = array_key_exists('stdPublic', $b) ? !empty($b['stdPublic']) : $oldPub;
                if ($pub !== $oldPub) {
                    require_perm_confirmed('angebote.loeschen');
                    $d[] = ['k' => 'ostd|pub', 'code' => '', 'name' => 'Wochenangebot', 'f' => 'Öffentlich ohne Anmeldung', 'from' => $oldPub ? 'ja' : 'nein', 'to' => $pub ? 'ja' : 'nein'];
                }
                $out = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => $me['name'], 'offers' => array_values($new), 'stdPublic' => $pub];
                store_write('angebote', $out);
                return [$out, $d];
            });
            [$out, $d] = $res;
            if ($d) audit('offers', 'Angebote geändert', $d);
            respond(['ok' => true, 'rev' => $out['rev'], 'offers' => $out['offers'], 'stdPublic' => $out['stdPublic']]);
        }
}
