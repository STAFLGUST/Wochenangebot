<?php
declare(strict_types=1);
/* Aktionen: Leergut · Leergutkonten und Abstimmung (Oberfläche leergut.intern, Daten und Regeln in
   app/api/module/leergut/leergut.php)
   Rechte (GR-103): leergut.sehen – Übersicht, Konten mit Bewegungen, Abstimmungen, Abschreibungen, Bilanz, CSV;
                    leergut.bearbeiten – Bewegungen buchen und stornieren, Auszüge erfassen und Status setzen,
                                         Abschreibungen und Inventur erfassen und ändern;
                    leergut.verwalten – Partner und Lademittel (Werte) pflegen, Datenpaket übernehmen.
   Gleichzeitiges Bearbeiten: Abstimmungen, Abschreibungen und Inventur tragen „rev“; ein veralteter Stand bekommt 409.
   Bewegungen werden nie geändert oder gelöscht, nur storniert (Status statt Löschen) – auch beim WinAB-Abgleich.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Index eines Eintrags einer Liste oder 404 */
function lg_index(array $doc, $id, string $was): int
{
    $id = is_string($id) ? $id : '';
    foreach ($doc['liste'] as $i => $e) if (($e['id'] ?? '') === $id && $id !== '') return $i;
    fail("$was nicht gefunden.", 404);
    return -1;
}
/* Veralteter Stand eines Eintrags → 409 mit dem aktuellen Eintrag */
function lg_rev_pruefen(array $b, array $alt, string $was): void
{
    if (array_key_exists('rev', $b) && (int)$b['rev'] !== (int)($alt['rev'] ?? 0))
        respond(['ok' => false, 'code' => 'konflikt', 'error' => "$was wurde inzwischen von " . ($alt['geaendert']['von'] ?? 'jemand anderem') . ' geändert. Bitte neu laden.', 'eintrag' => $alt], 409);
}
function lg_partner_name(array $stamm, string $id): string
{
    foreach ($stamm['partner'] as $p) if ($p['id'] === $id) return (string)$p['name'];
    return $id;
}

switch ($action) {
        /* Start: Stammdaten, Konten mit Salden, Abstimmungen mit Fristen, Abschreibungen, Inventur, eigene Rechte */
        case 'leergut_start': {
            $me = require_perm('leergut.sehen');
            header('Cache-Control: no-store');
            $heute = date('Y-m-d');
            $stamm = lg_stamm(); $bew = lg_doc('leergut-bewegungen')['liste']; $abst = lg_doc('leergut-abstimmungen')['liste'];
            $np = lg_nach_partner($bew);
            respond(['ok' => true, 'heute' => $heute, 'name' => $me['name'],
                     'rechte' => ['bearbeiten' => may($me, 'leergut.bearbeiten'), 'verwalten' => may($me, 'leergut.verwalten')],
                     'mandanten' => LG_MANDANTEN, 'arten' => LG_ARTEN, 'typen' => LG_TYPEN, 'abstStatus' => LG_ABST_STATUS, 'abschrStatus' => LG_ABSCHR_STATUS,
                     'lademittel' => $stamm['lademittel'], 'partner' => $stamm['partner'], 'konten' => lg_konten($stamm, $bew, $abst, $heute),
                     'abstimmungen' => array_map(function ($a) use ($np, $heute) { return lg_abstimmung_aus($a, $np, $heute); }, $abst),
                     'abschreibungen' => lg_doc('leergut-abschreibungen')['liste'], 'inventur' => lg_doc('leergut-inventur')['liste'],
                     'leer' => !$stamm['partner'] && !$bew]);
        }

        /* Konto eines Partners: alle Bewegungen (auch stornierte, nach Datum) und seine Abstimmungen */
        case 'leergut_konto': {
            require_perm('leergut.sehen');
            header('Cache-Control: no-store');
            $stamm = lg_stamm();
            $p = lg_partner_finden($stamm, $_GET['partner'] ?? '');
            $bew = lg_doc('leergut-bewegungen')['liste'];
            $eigene = array_values(array_filter($bew, function ($b) use ($p) { return $b['partner'] === $p['id']; }));
            usort($eigene, function ($a, $b) { return [$a['datum'], $a['erfasst']['t'] ?? ''] <=> [$b['datum'], $b['erfasst']['t'] ?? '']; });
            $np = lg_nach_partner($bew); $heute = date('Y-m-d');
            $abst = array_values(array_filter(lg_doc('leergut-abstimmungen')['liste'], function ($a) use ($p) { return $a['partner'] === $p['id']; }));
            usort($abst, function ($a, $b) { return strcmp($b['stichtag'], $a['stichtag']); });
            respond(['ok' => true, 'partner' => $p, 'bewegungen' => $eigene, 'abstimmungen' => array_map(function ($a) use ($np, $heute) { return lg_abstimmung_aus($a, $np, $heute); }, $abst)]);
        }

        /* Bilanz zum Stichtag: Salden aller Konten, eigener Bestand (Inventur), Summen und Wert */
        case 'leergut_bilanz': {
            require_perm('leergut.sehen');
            header('Cache-Control: no-store');
            $tag = lg_datum($_GET['stichtag'] ?? date('Y-m-d'), 'Stichtag');
            respond(['ok' => true, 'bilanz' => lg_bilanz($tag, lg_stamm(), lg_doc('leergut-bewegungen')['liste'], lg_doc('leergut-abstimmungen')['liste'], lg_doc('leergut-inventur')['liste'])]);
        }

        /* Bilanz zum Stichtag als CSV (Excel), im Protokoll vermerkt */
        case 'leergut_export': {
            require_perm('leergut.sehen', true);
            $b = body();
            $tag = lg_datum($b['stichtag'] ?? date('Y-m-d'), 'Stichtag');
            $stamm = lg_stamm();
            $bil = lg_bilanz($tag, $stamm, lg_doc('leergut-bewegungen')['liste'], lg_doc('leergut-abstimmungen')['liste'], lg_doc('leergut-inventur')['liste']);
            audit('leergut', 'Leergut: Bilanz zum ' . $tag . ' als CSV heruntergeladen (' . count($bil['zeilen']) . ' Konten)');
            header('Content-Type: text/csv; charset=utf-8');
            header('Content-Disposition: attachment; filename="Leergut-Bilanz_' . $tag . '.csv"');
            header('Cache-Control: private, no-store');
            header('X-Content-Type-Options: nosniff');
            echo lg_csv_bilanz($bil, $stamm);
            exit;
        }

        /* Bewegung buchen (immer neu; Ändern = stornieren und neu buchen) */
        case 'leergut_bewegung_save': {
            $me = require_perm('leergut.bearbeiten', true);
            $b = body();
            [$row, $name] = with_lock('leergut-bewegungen', function () use ($b, $me) {
                $stamm = lg_stamm();
                $row = lg_bewegung_pruefen($b, $stamm);
                $doc = lg_doc('leergut-bewegungen');
                if (count($doc['liste']) >= LG_MAX_BEWEGUNGEN) fail('Zu viele Bewegungen.', 422);
                $row = ['id' => lg_id('b')] + $row + ['quelle' => 'hand', 'erfasst' => lg_wer($me), 'storno' => null];
                $doc['liste'][] = $row;
                lg_schreiben('leergut-bewegungen', $doc);
                return [$row, lg_partner_name($stamm, $row['partner'])];
            });
            audit('leergut', 'Leergut: Bewegung gebucht – ' . $name . ', ' . $row['datum'] . ' (' . (LG_TYPEN[$row['typ']] ?? $row['typ']) . ')');
            respond(['ok' => true, 'bewegung' => $row]);
        }

        /* Bewegung stornieren (bleibt sichtbar, zählt nicht mehr) */
        case 'leergut_bewegung_storno': {
            $me = require_perm('leergut.bearbeiten', true);
            $b = body();
            $grund = lg_text($b['grund'] ?? '', 300, 'Grund');
            if ($grund === '') fail('Bitte einen Grund für das Stornieren angeben.', 422);
            [$row, $name] = with_lock('leergut-bewegungen', function () use ($b, $me, $grund) {
                $doc = lg_doc('leergut-bewegungen');
                $i = lg_index($doc, $b['id'] ?? '', 'Bewegung');
                if (!empty($doc['liste'][$i]['storno'])) fail('Diese Bewegung ist schon storniert.', 409);
                $doc['liste'][$i]['storno'] = lg_wer($me) + ['grund' => $grund];
                lg_schreiben('leergut-bewegungen', $doc);
                return [$doc['liste'][$i], lg_partner_name(lg_stamm(), $doc['liste'][$i]['partner'])];
            });
            audit('leergut', 'Leergut: Bewegung storniert – ' . $name . ', ' . $row['datum']);
            respond(['ok' => true, 'bewegung' => $row]);
        }

        /* Auszug eines Partners erfassen (ohne id) oder ändern (id + rev): Saldo laut Partner, Status, Frist */
        case 'leergut_abstimmung_save': {
            $me = require_perm('leergut.bearbeiten', true);
            $b = body();
            [$a, $name] = with_lock('leergut-bewegungen', function () use ($b, $me) {
                $stamm = lg_stamm(); $doc = lg_doc('leergut-abstimmungen');
                $id = (string)($b['id'] ?? '');
                $alt = null; $i = null;
                if ($id !== '') { $i = lg_index($doc, $id, 'Abstimmung'); $alt = $doc['liste'][$i]; lg_rev_pruefen($b, $alt, 'Die Abstimmung'); }
                elseif (count($doc['liste']) >= LG_MAX_ABSTIMMUNGEN) fail('Zu viele Abstimmungen.', 422);
                $a = lg_abstimmung_pruefen($b, $alt, $stamm);
                $np = lg_nach_partner(lg_doc('leergut-bewegungen')['liste']);
                $a['eigen'] = lg_saldo_bis($np[$a['partner']] ?? [], $a['stichtag']);   // Schnappschuss unseres Saldos (GR-106)
                if ($alt === null) {
                    $a = ['id' => lg_id('a')] + $a + ['erfasst' => lg_wer($me), 'verlauf' => []];
                    lg_verlauf($a, $me, 'erfasst (' . LG_ABST_STATUS[$a['status']] . ')');
                } else {
                    if (($alt['status'] ?? 'offen') !== $a['status']) lg_verlauf($a, $me, 'Status: ' . (LG_ABST_STATUS[$alt['status'] ?? 'offen'] ?? '') . ' → ' . LG_ABST_STATUS[$a['status']]);
                    elseif (($alt['saldo'] ?? []) != $a['saldo'] || $alt['stichtag'] !== $a['stichtag']) lg_verlauf($a, $me, 'Saldo oder Stichtag geändert');
                }
                $a['rev'] = (int)($a['rev'] ?? 0) + 1;
                $a['geaendert'] = lg_wer($me);
                if ($i === null) $doc['liste'][] = $a; else $doc['liste'][$i] = $a;
                lg_schreiben('leergut-abstimmungen', $doc);
                return [lg_abstimmung_aus($a, $np, date('Y-m-d')), lg_partner_name($stamm, $a['partner'])];
            });
            audit('leergut', 'Leergut: Abstimmung ' . $name . ' zum ' . $a['stichtag'] . ' gespeichert (' . LG_ABST_STATUS[$a['status']] . ')');
            respond(['ok' => true, 'abstimmung' => $a]);
        }

        /* Dachser-Abschreibung erfassen oder ändern (Status, WinAB-Auftrag, Notiz) */
        case 'leergut_abschreibung_save': {
            $me = require_perm('leergut.bearbeiten', true);
            $b = body();
            $d = with_lock('leergut-bewegungen', function () use ($b, $me) {
                $stamm = lg_stamm(); $doc = lg_doc('leergut-abschreibungen');
                $id = (string)($b['id'] ?? '');
                $alt = null; $i = null;
                if ($id !== '') { $i = lg_index($doc, $id, 'Abschreibung'); $alt = $doc['liste'][$i]; lg_rev_pruefen($b, $alt, 'Die Abschreibung'); }
                elseif (count($doc['liste']) >= LG_MAX_ABSCHREIBUNGEN) fail('Zu viele Abschreibungen.', 422);
                $d = lg_abschreibung_pruefen($b, $alt, $stamm);
                if ($alt === null) { $d = ['id' => lg_id('d')] + $d + ['erfasst' => lg_wer($me), 'verlauf' => []]; lg_verlauf($d, $me, 'erfasst'); }
                elseif (($alt['status'] ?? 'offen') !== $d['status']) lg_verlauf($d, $me, 'Status: ' . (LG_ABSCHR_STATUS[$alt['status'] ?? 'offen'] ?? '') . ' → ' . LG_ABSCHR_STATUS[$d['status']]);
                $d['rev'] = (int)($d['rev'] ?? 0) + 1;
                $d['geaendert'] = lg_wer($me);
                if ($i === null) $doc['liste'][] = $d; else $doc['liste'][$i] = $d;
                lg_schreiben('leergut-abschreibungen', $doc);
                return $d;
            });
            audit('leergut', 'Leergut: Abschreibung ' . $d['empfaenger'] . ' vom ' . $d['zugestellt'] . ' gespeichert (' . LG_ABSCHR_STATUS[$d['status']] . ')');
            respond(['ok' => true, 'abschreibung' => $d]);
        }

        /* Inventur (eigener Bestand zum Stichtag) erfassen oder ändern */
        case 'leergut_inventur_save': {
            $me = require_perm('leergut.bearbeiten', true);
            $b = body();
            $inv = with_lock('leergut-bewegungen', function () use ($b, $me) {
                $stamm = lg_stamm(); $doc = lg_doc('leergut-inventur');
                $id = (string)($b['id'] ?? '');
                $alt = null; $i = null;
                if ($id !== '') { $i = lg_index($doc, $id, 'Inventur'); $alt = $doc['liste'][$i]; lg_rev_pruefen($b, $alt, 'Die Inventur'); }
                elseif (count($doc['liste']) >= LG_MAX_INVENTUR) fail('Zu viele Inventuren.', 422);
                $inv = lg_inventur_pruefen($b, $alt, $stamm);
                if ($alt === null) $inv = ['id' => lg_id('i')] + $inv + ['erfasst' => lg_wer($me)];
                $inv['rev'] = (int)($inv['rev'] ?? 0) + 1;
                $inv['geaendert'] = lg_wer($me);
                if ($i === null) $doc['liste'][] = $inv; else $doc['liste'][$i] = $inv;
                lg_schreiben('leergut-inventur', $doc);
                return $inv;
            });
            audit('leergut', 'Leergut: Inventur zum ' . $inv['stichtag'] . ' gespeichert');
            respond(['ok' => true, 'inventur' => $inv]);
        }

        /* Partner anlegen (ohne id) oder ändern (id + rev); deaktivieren statt löschen */
        case 'leergut_partner_save': {
            $me = require_perm('leergut.verwalten', true);
            $b = body();
            $p = with_lock('leergut-bewegungen', function () use ($b, $me) {
                $stamm = lg_stamm();
                $id = (string)($b['id'] ?? ''); $i = null;
                if ($id !== '') {
                    foreach ($stamm['partner'] as $k => $x) if ($x['id'] === $id) $i = $k;
                    if ($i === null) fail('Partner nicht gefunden.', 404);
                    lg_rev_pruefen($b, $stamm['partner'][$i], 'Der Partner');
                } elseif (count($stamm['partner']) >= LG_MAX_PARTNER) fail('Zu viele Partner.', 422);
                $p = lg_partner_pruefen($b, $i !== null ? $stamm['partner'][$i] : null, $stamm);
                if ($i === null) $p = ['id' => lg_id('p')] + $p + ['erstellt' => lg_wer($me)];
                $p['rev'] = (int)($p['rev'] ?? 0) + 1;
                $p['geaendert'] = lg_wer($me);
                if ($i === null) $stamm['partner'][] = $p; else $stamm['partner'][$i] = $p;
                lg_schreiben('leergut-stamm', $stamm);
                return $p;
            });
            audit('leergut', 'Leergut: Partner „' . $p['name'] . '“ gespeichert' . (empty($p['aktiv']) ? ' (inaktiv)' : ''));
            respond(['ok' => true, 'partner' => $p]);
        }

        /* Lademittel und ihre Werte je Stück (Bewertung in der Bilanz) */
        case 'leergut_lademittel_save': {
            $me = require_perm('leergut.verwalten', true);
            $b = body();
            $lm = with_lock('leergut-bewegungen', function () use ($b) {
                $stamm = lg_stamm();
                $stamm['lademittel'] = lg_lademittel_pruefen($b['lademittel'] ?? null, $stamm['lademittel']);
                lg_schreiben('leergut-stamm', $stamm);
                return $stamm['lademittel'];
            });
            audit('leergut', 'Leergut: Lademittel und Werte gespeichert');
            respond(['ok' => true, 'lademittel' => $lm]);
        }

        /* WinAB-Bericht „Lademittelbewegungen Kunden“ abgleichen: vorschau (nichts gespeichert) oder übernehmen */
        case 'leergut_winab_import': {
            $me = require_perm('leergut.verwalten', true);
            $b = body();
            $vorschau = !empty($b['vorschau']);
            $erg = with_lock('leergut-bewegungen', function () use ($b, $me, $vorschau) {
                $stamm = lg_stamm();
                $w = lg_winab_pruefen($b, $stamm);
                if ($w['fehler']) return ['fehler' => $w['fehler']];
                $doc = lg_doc('leergut-bewegungen');
                [$stamm, $bew, $z, $neu, $summe] = lg_winab_abgleich($w, $stamm, $doc['liste'], $me);
                if (count($bew) > LG_MAX_BEWEGUNGEN) fail('Zu viele Bewegungen.', 422);
                if (!$vorschau) {
                    lg_schreiben('leergut-stamm', $stamm);
                    $doc['liste'] = $bew;
                    lg_schreiben('leergut-bewegungen', $doc);
                }
                return ['fehler' => [], 'zahlen' => $z, 'neueKunden' => array_slice($neu, 0, 50), 'summe' => $summe, 'bericht' => $w['bericht']];
            });
            if ($erg['fehler']) {
                if ($vorschau) respond(['ok' => true, 'fehler' => $erg['fehler']]);
                respond(['ok' => false, 'error' => 'Der Bericht enthält Fehler – nichts übernommen.', 'fehler' => $erg['fehler']], 422);
            }
            if (!$vorschau) {
                $z = $erg['zahlen']; $ber = $erg['bericht'];
                audit('leergut', 'Leergut: WinAB-Kundenbewegungen ' . $ber['von'] . ' bis ' . $ber['bis'] . ' abgeglichen – ' . $z['kunden'] . ' neue Kundenkonten, '
                    . $z['neu'] . ' neue Belege, ' . $z['geaendert'] . ' geändert, ' . $z['ausgeglichen'] . ' ausgeglichen');
            }
            respond(['ok' => true] + $erg);
        }

        /* Datenpaket prüfen (vorschau) und übernehmen – nur in ein leeres Modul oder mit „ersetzen“ */
        case 'leergut_import': {
            $me = require_perm('leergut.verwalten', true);
            $b = body();
            $erg = lg_paket_pruefen($b['paket'] ?? null, $me);
            $leer = lg_leer();
            if (!empty($b['vorschau'])) respond(['ok' => true, 'zahlen' => $erg['zahlen'], 'fehler' => $erg['fehler'], 'leer' => $leer]);
            if ($erg['fehler']) respond(['ok' => false, 'error' => 'Das Datenpaket enthält Fehler – nichts übernommen.', 'fehler' => $erg['fehler']], 422);
            with_lock('leergut-bewegungen', function () use ($erg, $b) {
                if (!lg_leer() && empty($b['ersetzen'])) fail('Im Modul sind schon Daten. Zum Ersetzen „Vorhandene Daten ersetzen“ wählen.', 409);
                $stamm = $erg['stamm']; $stamm['rev'] = lg_stamm()['rev'];
                lg_schreiben('leergut-stamm', $stamm);
                foreach (['bewegungen', 'abstimmungen', 'abschreibungen', 'inventur'] as $k) {
                    $alt = lg_doc('leergut-' . $k);
                    lg_schreiben('leergut-' . $k, ['rev' => $alt['rev'], 'liste' => $erg['docs'][$k]]);
                }
            });
            $z = $erg['zahlen'];
            audit('leergut', 'Leergut: Datenpaket übernommen' . ($leer ? '' : ' (vorhandene Daten ersetzt)') . ' – ' . $z['partner'] . ' Partner, ' . $z['bewegungen'] . ' Bewegungen, '
                . $z['abstimmungen'] . ' Abstimmungen, ' . $z['abschreibungen'] . ' Abschreibungen, ' . $z['inventur'] . ' Inventuren');
            respond(['ok' => true, 'zahlen' => $z]);
        }
}
