<?php
declare(strict_types=1);
/* Aktionen: CRM · Vertrieb (Oberfläche crm.intern, Daten und Regeln in app/api/module/crm/crm.php)
   Rechte (GR-103): crm.sehen – Kunden, Kundenblätter, Wiedervorlagen, Pipeline, Auswertung, Karte ansehen;
                    crm.bearbeiten – Kundenblätter, Interessenten und Aktivitäten erfassen;
                    crm.exportieren – Liste als CSV herunterladen.
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
            respond(['ok' => true, 'heute' => date('Y-m-d'), 'name' => $me['name'],
                     'rechte' => ['bearbeiten' => may($me, 'crm.bearbeiten'), 'exportieren' => may($me, 'crm.exportieren'), 'stammdaten' => may($me, 'kunden.bearbeiten')],
                     'kunden' => crm_liste(), 'vertreter' => crm_vertreter(), 'segmente' => CRM_SEGMENTE, 'phasen' => CRM_PHASEN, 'anruf' => CRM_ANRUF,
                     'arten' => CRM_ARTEN, 'rhythmen' => crm_rhythmen(), 'letzte' => array_map('crm_aktivitaet_aus', array_slice($akt, 0, 30)),
                     'statistik' => ['gesamt' => count($akt), 'jeArt' => $jeArt, 'tage30' => $tage30]]);
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
