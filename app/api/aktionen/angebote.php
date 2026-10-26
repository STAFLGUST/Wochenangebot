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
            if (strncmp($oid, 'e-', 2) === 0) {   // Einzelangebot: nur der Kunde selbst (freigegeben, gültig) oder Mitarbeiter mit Recht
                $e = einzel_von_kennung($oid);
                if (current_user()) { require_perm('einzelangebote.sehen'); if (!$e) fail('Unbekanntes Angebot.', 404); }
                elseif ($k = current_customer()) {
                    if (!empty($k['login']['mustChange'])) fail('Bitte zuerst ein eigenes Passwort festlegen.', 403);
                    if (!$e || $e['kid'] !== $k['id'] || !einzel_sichtbar($e)) fail('Dieses Angebot ist für Ihren Zugang nicht (mehr) verfügbar.', 403);
                } else fail('Bitte anmelden.', 401);
                header('Cache-Control: private, no-store');
                respond(['ok' => true, 'company' => $CFG['company'], 'offer' => einzel_model($e), 'fracht' => fracht_public()]);
            }
            if ($oid !== OFFER_STD || !std_public()) {
                // Mitarbeiter mit Modulzugang Angebot sehen alle Angebote; Kunden nur freigeschaltete; sonst Anmeldung nötig
                if (current_user()) require_modulzugang('angebot');
                elseif ($k = current_customer()) {
                    if (!empty($k['login']['mustChange'])) fail('Bitte zuerst ein eigenes Passwort festlegen.', 403);
                    if (!in_array($oid, customer_offers($k), true)) fail('Dieses Angebot ist für Ihren Zugang nicht freigeschaltet.', 403);
                } else fail('Bitte anmelden.', 401);
                header('Cache-Control: private, no-store');
            }
            $def = offer_def($oid);
            if (!$def) fail('Unbekanntes Angebot.', 404);
            if (!empty($_GET['draft'])) {
                require_modulzugang('angebot');
                $d = store_read('entwurf') ?? store_read('angebot');
                if (!$d) fail('Kein Entwurf vorhanden.', 404);
                respond(['ok' => true, 'company' => $CFG['company'], 'preview' => true, 'offer' => offer_resolve($d, $def), 'fracht' => fracht_public()]);
            }
            $published = store_read('angebot');
            if ($published === null) fail('Es ist noch kein Angebot veröffentlicht.', 404);
            $offer = offer_resolve($published, $def);
            if ($oid === OFFER_STD && std_public()) {
                // ETag über die aufgelöste Antwort: ausverkaufte Sonderposten (Bestand) und Hinweis/Fracht gehören dazu
                $etag = '"' . hash('sha256', json_encode($offer) . json_encode(fracht_public()) . ':std:3') . '"';
                header('ETag: ' . $etag);
                if (trim((string)($_SERVER['HTTP_IF_NONE_MATCH'] ?? '')) === $etag) { http_response_code(304); exit; }
            }
            respond(['ok' => true, 'company' => $CFG['company'], 'offer' => $offer, 'fracht' => fracht_public()]);
        }

        /* Liste der Kundenangebote (Name, Kennung, Rückfall – keine Preise): Angebot sowie Kundenverwaltung (Zuordnung) */
        case 'offers': {
            $me = require_auth();
            if (!modul_zugang_frei($me, 'angebot') && !may($me, 'kunden.sehen')) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            header('Cache-Control: no-store');
            $d = offers_load();
            respond(['ok' => true, 'rev' => $d['rev'], 'offers' => $d['offers'], 'std' => offer_def(OFFER_STD), 'stdPublic' => std_public()]);
        }

        case 'offers_save': {
            $me = require_perm('angebote.verwalten', true);
            $b = body();
            $list = [];
            $names = [];
            $in = is_array($b['offers'] ?? null) ? $b['offers'] : [];
            if (count($in) > OFFER_MAX) throw new InvalidArgumentException('Höchstens ' . OFFER_MAX . ' Kundenangebote.');
            foreach ($in as $o) {
                if (!is_array($o)) continue;
                $name = s($o['name'] ?? null, 80, false);
                if ($name === null || mb_strlen($name) < 2) throw new InvalidArgumentException('Jedes Angebot braucht einen Namen (mindestens 2 Zeichen).');
                $key = mb_strtolower($name);
                if (isset($names[$key]) || $key === 'wochenangebot') throw new InvalidArgumentException("Der Name „{$name}“ ist bereits vergeben.");
                $names[$key] = true;
                $id = (string)($o['id'] ?? '');
                if ($id === '' || $id === OFFER_STD || !preg_match('/^[a-z0-9-]{1,40}$/', $id)) throw new InvalidArgumentException('Ungültige Angebots-ID.');
                // „e-…“ ist Einzelangeboten vorbehalten; reine Zahlen werden in JSON zu Zahlenschlüsseln – beides nur für neue Angebote sperren
                if ((preg_match('/^e-/', $id) || ctype_digit($id)) && !in_array($id, offer_ids(), true)) throw new InvalidArgumentException("Die Angebots-ID „{$id}“ ist nicht erlaubt (beginnt mit „e-“ oder besteht nur aus Ziffern).");
                // ohne Angabe bleibt die bisherige Einstellung (unten unter der Sperre), sonst hidden|standard
                $row = ['id' => $id, 'name' => $name];
                if (array_key_exists('fallback', $o)) $row['fallback'] = $o['fallback'] === 'hidden' ? 'hidden' : 'standard';
                if (array_key_exists('gruppen', $o)) $row['gruppen'] = offer_gruppen_clean($o['gruppen'], $name);
                $list[] = $row;
            }
            if (count(array_unique(array_column($list, 'id'))) !== count($list)) throw new InvalidArgumentException('Angebots-IDs sind doppelt.');
            $res = with_lock('angebote', function () use ($b, $list, $me) {
                $cur = offers_load();
                if ((int)($b['rev'] ?? -1) !== (int)$cur['rev']) fail('Die Angebote wurden inzwischen an anderer Stelle geändert. Bitte die Seite neu laden.', 409);
                $old = []; foreach ($cur['offers'] as $o) $old[$o['id']] = $o;
                // IDs gelöschter Angebote werden nie wieder vergeben: im veröffentlichten Angebot, in der Historie und bei
                // Kunden (direkte Freischaltung) können noch Preise, Sonderpreise und Freischaltungen unter der alten ID stehen.
                $gesperrt = array_values(array_filter(is_array($cur['geloescht'] ?? null) ? $cur['geloescht'] : [], 'is_string'));
                $gesperrt = array_values(array_unique(array_merge($gesperrt, angebot_ids_mit_resten(array_keys($old)))));   // Löschungen vor dieser Fassung
                $belegt = array_flip(array_merge(array_keys($old), array_column($list, 'id'), $gesperrt));
                foreach ($list as $i => $o) {
                    if (isset($old[$o['id']]) || !in_array($o['id'], $gesperrt, true)) continue;
                    $basis = substr($o['id'], 0, 36); $k = 2;
                    while (isset($belegt["$basis-$k"])) $k++;
                    $list[$i]['id'] = "$basis-$k"; $belegt["$basis-$k"] = true;
                }
                foreach ($list as $i => $o) {
                    if (!array_key_exists('fallback', $o)) $list[$i]['fallback'] = ($old[$o['id']]['fallback'] ?? 'standard') === 'hidden' ? 'hidden' : 'standard';
                    // Felder, die dieser Stand nicht kennt (neuere Fassung), bleiben erhalten (GR-006); gruppen regelt der Block unten
                    if (isset($old[$o['id']])) $list[$i] += array_diff_key($old[$o['id']], array_flip(['id', 'name', 'fallback', 'gruppen']));
                }
                // Kundengruppen: ohne Angabe bleiben sie unverändert; neu zugeordnete Gruppen muss es geben
                $known = array_column(kundengruppen_load()['groups'], 'nr');
                $chk = function (array $neu, array $alt, string $name) use ($known) {
                    foreach (array_diff($neu, $alt) as $g) if (!in_array($g, $known, true)) throw new InvalidArgumentException("Die Kundengruppe $g gibt es nicht ($name). Bitte unter Stammdaten → Kundengruppen anlegen.");
                };
                foreach ($list as $i => $o) {
                    $alt = $old[$o['id']]['gruppen'] ?? [];
                    if (!array_key_exists('gruppen', $o)) { if ($alt) $list[$i]['gruppen'] = $alt; continue; }
                    $chk($o['gruppen'], $alt, $o['name']);
                    if (!$o['gruppen']) unset($list[$i]['gruppen']);
                }
                // Jede Kundengruppe gehört zu höchstens einem Angebot; Gruppen ohne Angebot bekommen das Wochenangebot
                $bei = [];
                foreach ($list as $o) foreach ($o['gruppen'] ?? [] as $g) {
                    if (isset($bei[$g])) throw new InvalidArgumentException("Die Kundengruppe $g ist bereits dem Angebot „{$bei[$g]}“ zugeordnet – jede Kundengruppe kann nur ein Angebot haben.");
                    $bei[$g] = $o['name'];
                }
                $stdAlt = $cur['stdGruppen'] ?? [];   // frühere Zuordnung zum Wochenangebot entfällt (gilt jetzt automatisch)
                $stdNeu = [];
                $new = []; foreach ($list as $o) $new[$o['id']] = $o;
                $removed = array_diff_key($old, $new);
                if ($removed) require_perm_confirmed('angebote.loeschen', 'angebote_loeschen');
                $d = [];
                $FB = ['standard' => 'Standardpreis zeigen', 'hidden' => 'Artikel ausblenden'];
                foreach ($new as $id => $o) {
                    if (!isset($old[$id])) { $d[] = ['k' => "o$id|+", 'code' => '', 'name' => $o['name'], 'f' => 'Neues Angebot', 'from' => '', 'to' => 'ohne eigenen Preis: ' . $FB[$o['fallback']]]; continue; }
                    if ($old[$id]['name'] !== $o['name']) $d[] = ['k' => "o$id|name", 'code' => '', 'name' => $o['name'], 'f' => 'Name', 'from' => $old[$id]['name'], 'to' => $o['name']];
                    if (($old[$id]['fallback'] ?? 'standard') !== $o['fallback']) $d[] = ['k' => "o$id|fb", 'code' => '', 'name' => $o['name'], 'f' => 'Ohne eigenen Preis', 'from' => $FB[$old[$id]['fallback'] ?? 'standard'], 'to' => $FB[$o['fallback']]];
                }
                foreach ($new as $id => $o) if (($old[$id]['gruppen'] ?? []) !== ($o['gruppen'] ?? []) && (isset($old[$id]) || !empty($o['gruppen']))) $d[] = ['k' => "o$id|grp", 'code' => '', 'name' => $o['name'], 'f' => 'Kundengruppen', 'from' => implode(', ', $old[$id]['gruppen'] ?? []), 'to' => implode(', ', $o['gruppen'] ?? [])];
                if ($stdNeu !== $stdAlt) $d[] = ['k' => 'ostd|grp', 'code' => '', 'name' => 'Wochenangebot', 'f' => 'Kundengruppen', 'from' => implode(', ', $stdAlt), 'to' => 'alle ohne eigenes Angebot'];
                foreach ($removed as $id => $o) $d[] = ['k' => "o$id|-", 'code' => '', 'name' => $o['name'], 'f' => 'Angebot gelöscht', 'from' => $o['name'], 'to' => ''];
                $oldPub = !array_key_exists('stdPublic', $cur) || !empty($cur['stdPublic']);
                $pub = array_key_exists('stdPublic', $b) ? !empty($b['stdPublic']) : $oldPub;
                if ($pub !== $oldPub) {
                    require_perm_confirmed('angebote.loeschen', 'angebote_loeschen');
                    $d[] = ['k' => 'ostd|pub', 'code' => '', 'name' => 'Wochenangebot', 'f' => 'Öffentlich ohne Anmeldung', 'from' => $oldPub ? 'ja' : 'nein', 'to' => $pub ? 'ja' : 'nein'];
                }
                $geloescht = array_values(array_unique(array_merge($gesperrt, array_map('strval', array_keys($removed)))));
                $out = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => $me['name'], 'offers' => array_values($new), 'stdPublic' => $pub,
                        'geloescht' => array_slice($geloescht, -2000)]
                     // weitere Felder einer neueren Fassung bleiben (GR-006); stdGruppen entfällt bewusst (gilt automatisch)
                     + array_diff_key($cur, array_flip(['rev', 'updatedAt', 'updatedBy', 'offers', 'stdPublic', 'geloescht', 'stdGruppen']));
                store_write('angebote', $out);
                return [$out, $d];
            });
            [$out, $d] = $res;
            if ($d) audit('offers', 'Angebote geändert', $d);
            respond(['ok' => true, 'rev' => $out['rev'], 'offers' => $out['offers'], 'stdPublic' => $out['stdPublic']]);
        }
}
