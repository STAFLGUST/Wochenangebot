<?php
declare(strict_types=1);
/* Angebot · Kundenangebot kopieren (Entscheidung des Inhabers 13.11.2026): ein Angebot als neues Kundenangebot anlegen und
   dabei alles außer den Kunden mitnehmen – eigene Preise (variants), eigene Bezeichnungen (namen), Empfehlungen und
   Sonderposten je Angebot (sale.offers), Werbung (meta.werbung) und die Regel der Artikelliste (fallback). Damit kommen auch
   ausgeblendete Artikel richtig mit: bei „eigener Artikelliste“ fehlt ihr Eintrag, bei „folgt dem Wochenangebot“ steht dort
   {status: hidden} – beides wird genau so übernommen. Kundengruppen bleiben leer (jede Gruppe gehört zu höchstens einem
   Angebot); Kunden sehen die Kopie erst mit zugeordneter Kundengruppe und nach dem Veröffentlichen.
   Quelle Wochenangebot: neues Angebot mit eigener Artikelliste aus allen Artikeln des Wochenangebots, der Wochenpreis wird
   eigener Preis (ohne Preis → „auf Anfrage“, wie beim Hinzufügen im Editor; Zusatzpreise entfallen wie in jedem
   Kundenangebot), dazu Empfehlungen und Werbung des Wochenangebots. Eigene Bezeichnungen gibt es im Wochenangebot nicht.
   Ablauf unter den Sperren entwurf → angebote (dieselbe Reihenfolge wie der Preisimport, module/angebot/import.php): erst
   alles prüfen – Revision des Entwurfs (409 wie save_draft), Stand der Angebotsliste (409 wie offers_save), Quelle (404),
   Name, höchstens OFFER_MAX –, dann die neue ID wie offers_save bilden (nie die ID eines gelöschten Angebots), Angebotsliste
   schreiben und die Kopie in den Entwurf schreiben (veröffentlicht wird wie immer im Modul Versand). Scheitert der Entwurf,
   wird die Angebotsliste zurückgesetzt. Rechte prüft die Aktion offer_kopieren (aktionen/angebote.php).
   Wird von der Aktion bei Bedarf geladen; schreibt nur eigene Dokumente (angebote, entwurf). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Gehört ein Artikel (Rohdaten des Entwurfs) zum Angebot? Gleiche Regel wie offer_resolve und inOffer() im Editor */
function angebot_kopie_enthalten(array $it, string $oid, string $fallback): bool
{
    $v = is_array($it['variants'] ?? null) ? ($it['variants'][$oid] ?? null) : null;
    $versteckt = is_array($v) && ($v['status'] ?? '') === 'hidden';
    if ($oid === OFFER_STD || $fallback !== 'hidden') return !$versteckt;
    return is_array($v) && !$versteckt;
}

/* Inhalte des Angebots $quelle im Modell unter der neuen ID $neu eintragen (ohne zu prüfen; clean_model folgt).
   Gibt [Modell, Zahlen] zurück – Zahlen für Antwort und Protokoll. */
function angebot_kopie_modell(array $m, string $quelle, string $neu): array
{
    $std = $quelle === OFFER_STD;
    $z = ['namen' => 0, 'empfehlungen' => 0, 'werbung' => false];
    foreach (is_array($m['items'] ?? null) ? $m['items'] : [] as $i => $it) {
        if (!is_array($it)) continue;
        if ($std) {
            // Wochenangebot: jeder Artikel, der dort nicht ausgeblendet ist, mit dem Wochenpreis als eigenem Preis
            if (angebot_kopie_enthalten($it, OFFER_STD, 'standard')) {
                $p = is_array($it['price'] ?? null) ? $it['price'] : [];
                $wert = $p['value'] ?? null;
                $m['items'][$i]['variants'][$neu] = ($p['status'] ?? '') === 'value' && (is_int($wert) || is_float($wert))
                    ? ['status' => 'value', 'value' => (float)$wert] : ['status' => 'request'];
            }
        } else {
            $v = is_array($it['variants'] ?? null) ? ($it['variants'][$quelle] ?? null) : null;
            if (is_array($v)) $m['items'][$i]['variants'][$neu] = $v;
            $nm = is_array($it['namen'] ?? null) ? ($it['namen'][$quelle] ?? null) : null;
            if (is_string($nm) && trim($nm) !== '') { $m['items'][$i]['namen'][$neu] = $nm; $z['namen']++; }
        }
        $so = is_array($it['sale'] ?? null) && is_array($it['sale']['offers'] ?? null) ? ($it['sale']['offers'][$quelle] ?? null) : null;
        if (is_array($so)) { $m['items'][$i]['sale']['offers'][$neu] = $so; $z['empfehlungen']++; }
    }
    $w = is_array($m['meta']['werbung'] ?? null) ? ($m['meta']['werbung'][$quelle] ?? null) : null;
    if (is_array($w)) { $m['meta']['werbung'][$neu] = $w; $z['werbung'] = true; }
    return [$m, $z];
}

/* Aktion offer_kopieren: {quelle, name, rev (Stand der Angebotsliste), revision (Stand des Entwurfs)} */
function angebot_kopieren(array $b, array $me): array
{
    $quelle = is_string($b['quelle'] ?? null) || is_int($b['quelle'] ?? null) ? (string)$b['quelle'] : '';
    if (!preg_match('/^[a-z0-9-]{1,40}$/', $quelle)) fail('Unbekanntes Angebot.', 404);
    $name = s($b['name'] ?? null, 80, false);
    if ($name === null || mb_strlen($name) < 2) fail('Bitte einen Namen für die Kopie angeben (mindestens 2 Zeichen).', 422);
    if (!array_key_exists('revision', $b) || !array_key_exists('rev', $b)) fail('Stand des Entwurfs oder der Angebote fehlt. Bitte die Seite neu laden.', 422);
    return with_lock('entwurf', function () use ($b, $quelle, $name, $me) {
        $dr = store_read('entwurf');
        if ((int)$b['revision'] !== draft_rev($dr)) draft_conflict($dr);
        return with_lock('angebote', function () use ($b, $quelle, $name, $me, $dr) {
            // 1. prüfen (vor dem ersten Schreiben – fail() schließt in der Datenbank sonst Halbfertiges ab)
            $vorher = store_read('angebote');
            $cur = offers_load();
            if ((int)$b['rev'] !== (int)$cur['rev']) fail('Die Angebote wurden inzwischen an anderer Stelle geändert. Bitte erneut versuchen.', 409);
            $def = offer_def($quelle);
            if (!$def) fail('Unbekanntes Angebot.', 404);
            $offers = $cur['offers'];
            if (count($offers) >= OFFER_MAX) fail('Höchstens ' . OFFER_MAX . ' Kundenangebote – bitte zuerst ein nicht mehr benötigtes Angebot löschen.', 422);
            $key = mb_strtolower($name);
            if ($key === 'wochenangebot') fail("Der Name „{$name}“ ist bereits vergeben.", 422);
            foreach ($offers as $o) if (mb_strtolower((string)$o['name']) === $key) fail("Der Name „{$name}“ ist bereits vergeben.", 422);
            // 2. neue ID wie offers_save/angebote_fuer_gruppen_anlegen: nie eine vorhandene oder die eines gelöschten Angebots
            $gesperrt = array_values(array_unique(array_merge(array_values(array_filter(is_array($cur['geloescht'] ?? null) ? $cur['geloescht'] : [], 'is_string')),
                angebot_ids_mit_resten(array_map('strval', array_column($offers, 'id'))))));
            $belegt = array_flip(array_merge(array_map('strval', array_column($offers, 'id')), $gesperrt, [OFFER_STD]));
            $basisId = angebot_slug($name); $id = $basisId; $k = 2;
            while (isset($belegt[$id])) $id = substr($basisId, 0, 36) . '-' . $k++;
            $fallback = $quelle === OFFER_STD || ($def['fallback'] ?? 'standard') === 'hidden' ? 'hidden' : 'standard';
            // 3. Angebotsliste schreiben (neues Angebot ohne Kundengruppen; weitere Felder einer neueren Fassung bleiben, GR-006)
            $offers[] = ['id' => $id, 'name' => $name, 'fallback' => $fallback];
            $out = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => $me['name'], 'offers' => array_values($offers)]
                 + array_diff_key($cur, array_flip(['rev', 'updatedAt', 'updatedBy', 'offers']));
            store_write('angebote', $out);
            // 4. Kopie in den Entwurf (ohne Entwurf: auf Basis des veröffentlichten Angebots; ohne beides nur das leere Angebot)
            $basis = $dr ?? store_read('angebot');
            $z = ['namen' => 0, 'empfehlungen' => 0, 'werbung' => false];
            $artikel = 0; $rev = draft_rev($dr); $dd = [];
            if (is_array($basis) && is_array($basis['items'] ?? null)) {
                try {
                    [$roh, $z] = angebot_kopie_modell($basis, $quelle, $id);
                    $model = clean_model($roh, false);
                    $model['savedAt'] = now();
                    $model['savedBy'] = $me['name'];
                    $model['rev'] = $rev = draft_rev($dr) + 1;
                    store_write('entwurf', $model);
                } catch (Throwable $e) {
                    // Angebotsliste zurück (Dateien; in der Datenbank setzt die Sperre ohnehin alles zurück)
                    if ($vorher === null) store_delete('angebote'); else store_write('angebote', $vorher);
                    throw $e;
                }
                foreach ($model['items'] as $it) if (angebot_kopie_enthalten($it, $id, $fallback)) $artikel++;
                $dd = changes_between($basis, $model);
            }
            $FB = ['standard' => 'folgt dem Wochenangebot', 'hidden' => 'eigene Artikelliste'];
            $d = array_merge([['k' => "o$id|+", 'code' => '', 'name' => $name, 'f' => 'Neues Angebot (Kopie von „' . $def['name'] . '“)', 'from' => '',
                               'to' => 'Artikelliste: ' . $FB[$fallback] . ', ohne Kundengruppen']], $dd);
            $teile = [$artikel === 1 ? '1 Artikel' : $artikel . ' Artikel'];
            if ($z['namen']) $teile[] = $z['namen'] === 1 ? '1 eigene Bezeichnung' : $z['namen'] . ' eigene Bezeichnungen';
            if ($z['empfehlungen']) $teile[] = $z['empfehlungen'] === 1 ? '1 Empfehlung' : $z['empfehlungen'] . ' Empfehlungen';
            if ($z['werbung']) $teile[] = 'Werbung';
            audit('offers', "Angebot „{$name}“ als Kopie von „{$def['name']}“ angelegt – " . implode(', ', $teile)
                . ' (ohne Kundengruppen; im Entwurf, für Kunden erst nach Zuordnung und Veröffentlichen)', array_slice($d, 0, 2000));
            return ['id' => $id, 'name' => $name, 'fallback' => $fallback, 'artikel' => $artikel, 'namen' => $z['namen'], 'empfehlungen' => $z['empfehlungen'],
                    'werbung' => $z['werbung'], 'rev' => $out['rev'], 'offers' => $out['offers'], 'stdPublic' => std_public(), 'revision' => $rev];
        });
    });
}
