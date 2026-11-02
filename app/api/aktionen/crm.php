<?php
declare(strict_types=1);
/* Aktionen: CRM · Vertrieb (Oberfläche crm.intern, Daten und Regeln in app/api/module/crm/crm.php)
   Rechte (GR-103): crm.sehen – Kunden, Kundenblätter, Wiedervorlagen, Pipeline, Auswertung, Karte ansehen (crm_karte);
                    crm.bearbeiten – Kundenblätter, Interessenten und Aktivitäten erfassen;
                    crm.exportieren – Liste als CSV herunterladen;
                    crm.mhd_ware – Reiter „MHD-Ware“: Artikel kurz vor Ablauf und ihre Käufer (Wiedervorlage dazu zusätzlich crm.bearbeiten);
                    crm.master – Master-Cockpit und Ansicht anderer Vertreter; crm.umsatz_euro / crm.umsatz_kg – Umsätze in € bzw.
                    Mengen in kg im Cockpit und im Kunden-Pop-up (module/crm/cockpit.php);
                    einzelangebote.sehen / .bearbeiten (wie im Eingabebereich) – Einzelangebote beim Kunden (module/crm/einzelangebot.php).
   Kundenstammdaten liest das CRM nur (Eigentümer Verwaltung, E-1); geändert werden sie in der Verwaltung.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Schlüssel aus der Anfrage (Kunden-ID der Verwaltung oder Interessent „i…“) */
function crm_key_param($v): string
{
    $k = is_string($v) ? trim($v) : '';
    if (!preg_match('/^[A-Za-z0-9_-]{1,40}$/', $k) || !crm_schluessel_gueltig($k)) fail('Kunde nicht gefunden.', 404);
    return $k;
}
/* Ein Eintrag der Liste (nach dem Speichern an die Oberfläche zurück) */
function crm_eintrag(string $key): ?array
{
    foreach (crm_liste() as $e) if ($e['key'] === $key) return $e;
    return null;
}

switch ($action) {
        /* Start: Kunden der Verwaltung und Interessenten mit Kundenblatt, Vertreter, Auswahllisten, letzte Aktivitäten */
        case 'crm_start': {
            $me = require_perm('crm.sehen');
            header('Cache-Control: no-store');
            $akt = array_reverse(crm_aktivitaeten_doc()['liste']);   // zuletzt erfasst zuerst (auch bei gleicher Sekunde)
            usort($akt, function ($a, $b) { return strcmp($b['at'], $a['at']); });
            $jeArt = array_fill_keys(CRM_ARTEN, 0); $tage30 = 0; $seit = gmdate('Y-m-d\TH:i:s\Z', time() - 30 * 86400);
            foreach ($akt as $a) { if (isset($jeArt[$a['art']])) $jeArt[$a['art']]++; if ($a['at'] >= $seit) $tage30++; }
            respond(['ok' => true, 'heute' => date('Y-m-d'), 'name' => $me['name'], 'ich' => (string)($me['vertreter'] ?? ''),
                     'rechte' => ['bearbeiten' => may($me, 'crm.bearbeiten'), 'exportieren' => may($me, 'crm.exportieren'), 'stammdaten' => may($me, 'kunden.bearbeiten'), 'mhd' => may($me, 'crm.mhd_ware')]
                                 + crm_zahlrechte($me) + ['einzel' => may($me, 'einzelangebote.sehen'), 'einzelBearbeiten' => may($me, 'einzelangebote.bearbeiten')],
                     'kunden' => crm_liste(), 'vertreter' => crm_vertreter(), 'segmente' => CRM_SEGMENTE, 'phasen' => CRM_PHASEN, 'anruf' => CRM_ANRUF,
                     'arten' => CRM_ARTEN, 'rhythmen' => crm_rhythmen(), 'letzte' => array_map('crm_aktivitaet_aus', array_slice($akt, 0, 30)),
                     'statistik' => ['gesamt' => count($akt), 'jeArt' => $jeArt, 'tage30' => $tage30]]);
        }

        /* Cockpit: Mein Cockpit (eigener Vertreter) bzw. mit crm.master das Master-Cockpit (?vertreter=alle) oder die Ansicht eines
           Vertreters (?vertreter=<Nummer>, „_“ = Kunden ohne Vertreter) – Zahlen nur mit crm.umsatz_euro bzw. crm.umsatz_kg */
        case 'crm_cockpit': {
            $me = require_perm('crm.sehen');
            header('Cache-Control: no-store');
            $w = $_GET['vertreter'] ?? null;
            if ($w !== null && (!is_string($w) || !preg_match('/^[0-9A-Za-z._-]{0,10}$/', $w))) fail('Ungültiger Vertreter.', 422);
            respond(crm_cockpit($me, $w));
        }

        /* Kunden-Pop-up, Reiter „Übersicht“: Umsätze, Signale und Artikel eines Kunden aus den Umsatzdaten (wie das Cockpit nach Rechten) */
        case 'crm_kunde_umsatz': {
            $me = require_perm('crm.sehen');
            header('Cache-Control: no-store');
            respond(crm_kunde_umsatz($me, crm_key_param($_GET['key'] ?? '')));
        }

        /* Einzelangebote eines Kunden (Kunden-Pop-up, Reiter „Angebote“) – Liste ohne Positionen, dazu E-Mail und Portalzugang des Kunden */
        case 'crm_einzel_liste': {
            $me = crm_einzel_recht('sehen');
            header('Cache-Control: no-store');
            $c = crm_einzel_kunde($_GET['key'] ?? '');
            respond(['ok' => true, 'liste' => einzel_liste((string)$c['id']), 'email' => (string)($c['email'] ?? ''), 'portal' => !empty($c['login']['active']),
                     'bearbeiten' => may($me, 'einzelangebote.bearbeiten'), 'heute' => date('Y-m-d')]);
        }
        case 'crm_einzel_detail': {
            crm_einzel_recht('sehen');
            header('Cache-Control: no-store');
            $c = crm_einzel_kunde($_GET['key'] ?? '');
            respond(['ok' => true, 'angebot' => einzel_view(crm_einzel_von($c, $_GET['id'] ?? ''), einzel_kunden_map()), 'fracht' => fracht_hinweis()]);
        }
        case 'crm_einzel_pdf': {
            crm_einzel_recht('sehen');
            einzel_pdf_senden(crm_einzel_von(crm_einzel_kunde($_GET['key'] ?? ''), $_GET['id'] ?? ''));
        }
        case 'crm_einzel_artikel': {
            $me = crm_einzel_recht('bearbeiten');
            header('Cache-Control: no-store');
            respond(['ok' => true] + crm_einzel_artikel($me));
        }
        /* Anlegen oder ändern: der Kunde kommt aus dem Schlüssel (ein mitgeschickter Kunde wird ignoriert) */
        case 'crm_einzel_save': {
            $me = crm_einzel_recht('bearbeiten', true);
            $b = body();
            $c = crm_einzel_kunde($b['key'] ?? '');
            if (is_string($b['id'] ?? null) && $b['id'] !== '') crm_einzel_von($c, $b['id']);
            respond(['ok' => true, 'angebot' => einzel_speichern(['kid' => (string)$c['id']] + $b, $me)]);
        }
        case 'crm_einzel_status': {
            $me = crm_einzel_recht('bearbeiten', true);
            $b = body();
            crm_einzel_von(crm_einzel_kunde($b['key'] ?? ''), $b['id'] ?? '');
            respond(['ok' => true, 'angebot' => einzel_status_setzen($b, $me)]);
        }
        case 'crm_einzel_loeschen': {
            crm_einzel_recht('bearbeiten', true);
            $b = body();
            $e = crm_einzel_von(crm_einzel_kunde($b['key'] ?? ''), $b['id'] ?? '');
            einzel_entfernen($e['id']);
            respond(['ok' => true]);
        }
        /* Per E-Mail an den Kunden – mit derselben Bestätigung wie im Eingabebereich (Schlüssel einzel_senden) */
        case 'crm_einzel_senden': {
            $me = require_perm_confirmed('einzelangebote.bearbeiten', 'einzel_senden');
            if (!may($me, 'crm.sehen')) fail('Dafür fehlt Ihnen die Berechtigung „CRM ansehen“.', 403);
            $b = body();
            crm_einzel_von(crm_einzel_kunde($b['key'] ?? ''), $b['id'] ?? '');
            $cfg = require_mail();
            respond(['ok' => true, 'angebot' => einzel_mail($b, $me, $cfg)]);
        }

        /* Karte: Koordinaten der Anschriften (Hausnummer bzw. Straße) aus dem Adressverzeichnis auf dem Server; ohne Eintrag
           zeigt die Karte den PLZ-Mittelpunkt. Stand: Anzahl und Datum des Verzeichnisses oder null (nicht geladen) */
        case 'crm_karte': {
            require_perm('crm.sehen');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'stand' => adressen_stand(), 'punkte' => (object)crm_karte_punkte()]);
        }

        /* Verlauf eines Kunden (neueste zuerst) */
        case 'crm_verlauf': {
            require_perm('crm.sehen');
            header('Cache-Control: no-store');
            $key = crm_key_param($_GET['key'] ?? '');
            $liste = array_reverse(array_values(array_filter(crm_aktivitaeten_doc()['liste'], function ($a) use ($key) { return $a['key'] === $key; })));
            usort($liste, function ($a, $b) { return strcmp($b['at'], $a['at']); });
            respond(['ok' => true, 'key' => $key, 'aktivitaeten' => array_map('crm_aktivitaet_aus', $liste)]);
        }

        /* Kundenblatt ändern: nur die mitgeschickten Felder (gleichzeitiges Bearbeiten verschiedener Felder überschreibt nichts) */
        case 'crm_kunde_save': {
            $me = require_perm('crm.bearbeiten', true);
            $b = body();
            $key = crm_key_param($b['key'] ?? '');
            if (!is_array($b['felder'] ?? null) || !$b['felder']) fail('Keine Änderungen übermittelt.', 422);
            $F = crm_felder();
            $neu = [];
            foreach ($b['felder'] as $f => $v) {
                if (!isset($F[$f])) fail('Unbekanntes Feld: ' . substr((string)$f, 0, 40), 422);
                $neu[$f] = ($F[$f][1])($v);
            }
            [, $nr] = crm_firma_nr($key);
            $aktiv = crm_ist_aktiv($key);   // Vergleich mit dem angezeigten Standard (inaktive Kunden: „Aktiv in der Wiedervorlage“ = nein)
            with_lock('crm-kunden', function () use ($key, $neu, $me, $nr, $aktiv) {
                $doc = crm_kunden_doc();
                $alt = $doc['eintraege'][$key] ?? [];
                $d = crm_protokoll_aenderungen($key, $nr, crm_blatt($alt, $key[0] === 'i', $aktiv), $neu);
                if (!$d) return;
                $doc['eintraege'][$key] = array_merge($alt, $neu, ['geaendert' => now(), 'geaendertVon' => $me['name']]);
                crm_schreiben('crm-kunden', $doc);
                audit('crm', 'CRM: Kundenblätter bearbeitet', $d, null, true);
            });
            respond(['ok' => true, 'kunde' => crm_eintrag($key)]);
        }

        /* Aktivität protokollieren; setzt „Letzter Kontakt“ und bei Angabe den nächsten Schritt mit Wiedervorlage */
        case 'crm_aktivitaet': {
            $me = require_perm('crm.bearbeiten', true);
            $b = body();
            $key = crm_key_param($b['key'] ?? '');
            $art = crm_wahl($b['art'] ?? '', CRM_ARTEN, 'Art', false);
            $notiz = crm_text($b['notiz'] ?? '', 500, 'Ergebnis / Betreff');
            $naechster = crm_text($b['naechster'] ?? '', 160, 'Nächster Schritt');
            $faellig = crm_datum($b['faellig'] ?? '', 'Wiedervorlage');
            if ($notiz === '' && $naechster === '') fail('Bitte Ergebnis oder nächsten Schritt eintragen.', 422);
            if ($faellig !== '' && $naechster === '') fail('Für eine Wiedervorlage bitte den nächsten Schritt angeben.', 422);
            [$firma, $nr] = crm_firma_nr($key);
            $heute = date('Y-m-d');
            $a = with_lock('crm-kunden', function () use ($key, $art, $notiz, $naechster, $faellig, $firma, $nr, $me, $heute) {
                $akt = crm_aktivitaeten_doc();
                $e = ['id' => crm_id('a'), 'key' => $key, 'art' => $art, 'notiz' => $notiz, 'naechster' => $naechster, 'faellig' => $faellig,
                      'at' => now(), 'von' => $me['name'], 'vonId' => $me['id'], 'firma' => $firma, 'nr' => $nr];   // Schnappschuss (GR-106)
                $akt['liste'][] = $e;
                if (count($akt['liste']) > CRM_MAX_AKTIVITAETEN) $akt['liste'] = array_slice($akt['liste'], -CRM_MAX_AKTIVITAETEN);
                crm_schreiben('crm-aktivitaeten', $akt);
                $doc = crm_kunden_doc();
                $blatt = $doc['eintraege'][$key] ?? [];
                $blatt['letzterKontakt'] = $heute;
                if ($art === 'Bestellung') $blatt['letzterAuftrag'] = $heute;
                if ($naechster !== '') { $blatt['naechsterSchritt'] = $naechster; $blatt['wiedervorlage'] = $faellig; }
                $doc['eintraege'][$key] = array_merge($blatt, ['geaendert' => now(), 'geaendertVon' => $me['name']]);
                crm_schreiben('crm-kunden', $doc);
                return $e;
            });
            respond(['ok' => true, 'aktivitaet' => crm_aktivitaet_aus($a), 'kunde' => crm_eintrag($key)]);
        }

        /* Interessent anlegen oder ändern (eigene Adressangaben; Kunden der Verwaltung ändert das CRM nie) */
        case 'crm_interessent_save': {
            $me = require_perm('crm.bearbeiten', true);
            $b = body();
            $id = is_string($b['id'] ?? null) ? $b['id'] : '';
            $res = with_lock('crm-kunden', function () use ($b, $id, $me) {
                $doc = crm_interessenten_doc();
                $idx = null;
                foreach ($doc['liste'] as $i => $x) if ($x['id'] === $id) $idx = $i;
                if ($id !== '' && $idx === null) fail('Interessent nicht gefunden.', 404);
                if ($idx === null && count($doc['liste']) >= CRM_MAX_INTERESSENTEN) fail('Zu viele Interessenten (höchstens ' . CRM_MAX_INTERESSENTEN . ').', 422);
                $alt = $idx !== null ? $doc['liste'][$idx] : null;
                $row = crm_interessent_pruefen($b, $alt);
                $row = ['id' => $alt['id'] ?? crm_id('i')] + $row + ['erstellt' => $alt['erstellt'] ?? now(), 'erstelltVon' => $alt['erstelltVon'] ?? $me['name'],
                        'geaendert' => now(), 'geaendertVon' => $me['name']];
                if ($idx === null) $doc['liste'][] = $row; else $doc['liste'][$idx] = $row;
                crm_schreiben('crm-interessenten', $doc);
                return ['id' => $row['id'], 'neu' => $idx === null];
            });
            audit('crm', $res['neu'] ? 'CRM: Interessent angelegt' : 'CRM: Interessent geändert');
            respond(['ok' => true, 'kunde' => crm_eintrag($res['id'])]);
        }

        /* MHD-Ware: Artikel der MHD-Liste des Bestands (ohne Preise) mit der Zahl ihrer Käufer im Zeitraum (?monate=3|6|12) und die
           Artikel der Umsatzdaten für die Suche nach einem anderen Artikel */
        case 'crm_mhd': {
            $me = require_perm('crm.mhd_ware');
            header('Cache-Control: no-store');
            $monate = crm_mhd_monate($_GET['monate'] ?? null);
            $l = crm_mhd_liste();
            [$von, $bis] = crm_mhd_zeitraum($monate, $l['heute']);
            $k = umsatzdaten_kaeufer(array_column($l['zeilen'], 'code'), $von, $bis);
            $artikel = array_map(function ($a) use ($k) { return $a + ['kaeufer' => count($k['artikel'][$a['code']] ?? [])]; }, $l['zeilen']);
            $alle = [];
            foreach (umsatzdaten_artikelliste() as $nr => $name) $alle[] = ['nr' => (string)$nr, 'name' => $name];
            respond(['ok' => true, 'heute' => $l['heute'], 'bestand' => $l['stand'], 'umsatzBis' => $k['stand'], 'monate' => $monate, 'von' => $von, 'bis' => $bis,
                     'artikel' => $artikel, 'alle' => $alle, 'rechte' => ['bearbeiten' => may($me, 'crm.bearbeiten'), 'exportieren' => may($me, 'crm.exportieren')]]);
        }

        /* MHD-Ware: Käufer eines Artikels im Zeitraum (?artikel=…&monate=3|6|12) – Menge, Käufe (Liefertage), letzter Kauf, Schlüssel
           des Kundenblatts; keine Beträge */
        case 'crm_mhd_kaeufer': {
            require_perm('crm.mhd_ware');
            header('Cache-Control: no-store');
            $code = crm_artikel_code($_GET['artikel'] ?? '');
            $monate = crm_mhd_monate($_GET['monate'] ?? null);
            $l = crm_mhd_liste();
            [$von, $bis] = crm_mhd_zeitraum($monate, $l['heute']);
            $artikel = crm_mhd_artikel($code, $l);
            $k = umsatzdaten_kaeufer([$code], $von, $bis);
            $keys = crm_key_je_nr();
            $kaeufer = array_map(function ($x) use ($keys) { return $x + ['key' => $keys[code_key($x['kunde'])] ?? null]; }, $k['artikel'][$code] ?? []);
            usort($kaeufer, function ($a, $b) { return strcmp((string)$b['zuletzt'], (string)$a['zuletzt']) ?: $b['kaeufe'] <=> $a['kaeufe'] ?: strcmp($a['kunde'], $b['kunde']); });
            respond(['ok' => true, 'artikel' => $artikel, 'monate' => $monate, 'von' => $von, 'bis' => $bis, 'umsatzBis' => $k['stand'], 'kaeufer' => $kaeufer]);
        }

        /* MHD-Ware: Wiedervorlage für ausgewählte Käufer. Je Kunde eine Notiz „MHD-Ware anbieten: …“ im Verlauf (einmal je Artikel
           und MHD, Schnappschuss von Firma und Nummer, GR-106) und die Wiedervorlage am gewählten Tag (eine frühere bleibt).
           Der nächste Schritt wird nie gekürzt oder überschrieben: leer → der Hinweis; sonst wird der Hinweis nur vorangestellt,
           wenn beides zusammen in 160 Zeichen passt (sonst steht er nur im Verlauf). Artikelname und MHD nimmt der Server aus
           MHD-Liste bzw. Umsatzdaten, nie aus dem Browser. Protokoll wie beim Kundenblatt (Wiedervorlage mit altem Wert). */
        case 'crm_mhd_wiedervorlage': {
            $me = require_perm('crm.bearbeiten', true);
            if (!may($me, 'crm.mhd_ware')) fail('Dafür fehlt Ihnen die Berechtigung „CRM: MHD-Ware“.', 403);
            $b = body();
            $code = crm_artikel_code($b['artikel'] ?? '');
            $datum = crm_datum($b['datum'] ?? '', 'Wiedervorlage');
            if ($datum === '') $datum = date('Y-m-d');
            $roh = $b['kunden'] ?? null;
            if (!is_array($roh) || !array_is_list($roh) || !$roh) fail('Bitte mindestens einen Kunden auswählen.', 422);
            if (count($roh) > CRM_MHD_MAX_KUNDEN) fail('Höchstens ' . CRM_MHD_MAX_KUNDEN . ' Kunden auf einmal.', 422);
            $gueltig = crm_schluessel_menge();
            $keys = [];
            foreach ($roh as $k) {
                $k = is_string($k) ? trim($k) : '';
                if (!preg_match('/^[A-Za-z0-9_-]{1,40}$/', $k) || !isset($gueltig[$k])) fail('Kunde nicht gefunden.', 404);
                $keys[$k] = true;
            }
            $keys = array_keys($keys);
            $schritt = crm_mhd_schritt(crm_mhd_artikel($code, crm_mhd_liste()));
            [$n, $d] = with_lock('crm-kunden', function () use ($keys, $schritt, $datum, $me, $gueltig) {
                $doc = crm_kunden_doc();
                $akt = crm_aktivitaeten_doc();
                $notiert = [];
                foreach ($akt['liste'] as $a) if (($a['notiz'] ?? '') === $schritt) $notiert[$a['key']] = true;
                $d = [];
                foreach ($keys as $key) {
                    $alt = $doc['eintraege'][$key] ?? [];
                    $altSchritt = (string)($alt['naechsterSchritt'] ?? '');
                    $kombi = $schritt . ' · ' . $altSchritt;
                    $neuSchritt = $altSchritt === '' ? $schritt : (str_contains($altSchritt, $schritt) || mb_strlen($kombi) > 160 ? $altSchritt : $kombi);
                    $altWv = (string)($alt['wiedervorlage'] ?? '');
                    $neu = ['naechsterSchritt' => $neuSchritt, 'wiedervorlage' => $altWv !== '' && $altWv <= $datum ? $altWv : $datum];
                    [$firma, $nr, $istAktiv] = $gueltig[$key];
                    $d = array_merge($d, crm_protokoll_aenderungen($key, $nr, crm_blatt($alt, $key[0] === 'i', $istAktiv), $neu));
                    if ($neu['naechsterSchritt'] !== $altSchritt || $neu['wiedervorlage'] !== $altWv)
                        $doc['eintraege'][$key] = array_merge($alt, $neu, ['geaendert' => now(), 'geaendertVon' => $me['name']]);
                    if (!isset($notiert[$key]))
                        $akt['liste'][] = ['id' => crm_id('a'), 'key' => $key, 'art' => 'Notiz', 'notiz' => $schritt, 'naechster' => '', 'faellig' => $neu['wiedervorlage'],
                                           'at' => now(), 'von' => $me['name'], 'vonId' => $me['id'], 'firma' => $firma, 'nr' => $nr];   // Schnappschuss (GR-106)
                }
                if (count($akt['liste']) > CRM_MAX_AKTIVITAETEN) $akt['liste'] = array_slice($akt['liste'], -CRM_MAX_AKTIVITAETEN);
                crm_schreiben('crm-aktivitaeten', $akt);
                crm_schreiben('crm-kunden', $doc);
                return [count($keys), $d];
            });
            audit('crm', 'CRM: Wiedervorlage für MHD-Ware (' . $n . ($n === 1 ? ' Kunde)' : ' Kunden)'), $d);   // eigener Eintrag mit den Änderungen (Wiedervorlage mit altem Wert)
            $set = array_flip($keys);
            respond(['ok' => true, 'anzahl' => $n, 'kunden' => array_values(array_filter(crm_liste(), function ($e) use ($set) { return isset($set[$e['key']]); }))]);
        }

        /* Liste als CSV (Excel) – nur mit eigenem Recht, im Protokoll vermerkt */
        case 'crm_export': {
            $me = require_perm('crm.exportieren', true);
            $liste = crm_liste();
            audit('crm', 'CRM: Liste als CSV heruntergeladen (' . count($liste) . ' Einträge)');
            $name = 'CRM_' . date('Y-m-d') . '.csv';
            header('Content-Type: text/csv; charset=utf-8');
            header('Content-Disposition: attachment; filename="' . $name . '"');
            header('Cache-Control: private, no-store');
            header('X-Content-Type-Options: nosniff');
            echo crm_csv($liste, crm_vertreter());
            exit;
        }
}
