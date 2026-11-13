<?php
declare(strict_types=1);
/* STAFL-Plattform · Angebot · Sonderangebote (Auftrag des Inhabers 13.11.2026): ein Angebot für ganze Kundengruppen mit
   Gültigkeit – Zeitraum (von–bis, beide Tage eingeschlossen) oder Kalenderwoche (Montag bis Sonntag nach ISO 8601), immer in
   deutscher Zeit (Europe/Berlin).

   Ein Sonderangebot ist ein Angebot im gemeinsamen Angebotsmodell – Eintrag im Dokument „angebote“ (nur erweitert, GR-006):
     {id: 'sonder-…', name, fallback: 'hidden', art: 'sonder',
      gueltig: {modus: 'zeitraum', von: 'JJJJ-MM-TT', bis: 'JJJJ-MM-TT'} | {modus: 'kw', jahr, kw},
      sonderGruppen: [Nummer der Kundengruppe …], angelegt: {t, von}, geaendert?: {t, von}, beendet?: {t, von}}
   Inhalte (Artikel, Preise, Bezeichnungen, Werbung, Empfehlungen) stehen wie bei jedem Kundenangebot mit eigener Artikelliste
   im Entwurf bzw. im veröffentlichten Angebot (variants[<id>], namen[<id>], sale.offers[<id>], meta.werbung[<id>]) – bearbeitet
   im gewohnten Editor, veröffentlicht im Modul Versand mit allen Angeboten zusammen, aufgelöst nur in offer_resolve().

   Sichtbar für einen Kunden nur, wenn (alles serverseitig, customer_offers() in lib/kunden.php):
     – seine Kundengruppe in sonderGruppen steht (nie direkt beim Kunden freigeschaltet),
     – heute im Zeitraum liegt und das Angebot nicht vorzeitig beendet ist (sonder_status = „laeuft“),
     – das veröffentlichte Angebot Artikel dieses Sonderangebots enthält.
   Nie im öffentlichen Wochenangebot (GR-002). Die Gruppen stehen bewusst nicht in „gruppen“: dort gilt „jede Kundengruppe
   höchstens ein Angebot“ (eine Gruppe hat ihr Wochen- bzw. Kundenangebot UND gültige Sonderangebote), und ältere Fassungen
   zeigten ein Angebot mit „gruppen“ ohne Gültigkeit dauerhaft – mit „sonderGruppen“ sehen Kunden es nach einem Rückfall nicht.
   Abgelaufene Sonderangebote bleiben gespeichert, bis sie jemand löscht.

   Aktionen (aktionen/angebote.php): sonderangebote (Liste), sonderangebot_save (anlegen, ändern, beenden, fortsetzen –
   angebote.verwalten), sonderangebot_loeschen (angebote.loeschen mit Bestätigung „angebote_loeschen“). offers_save legt
   Sonderangebote nie an, ändert und löscht sie nicht. Geladen von lib/angebote.php (immer, auch im Dienst „postausgang“). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const SONDER_ART = 'sonder';
const SONDER_PRAEFIX = 'sonder-';   // IDs neuer Sonderangebote; neue Kundenangebote dürfen so nicht beginnen (offers_save)
const SONDER_MAX = 500;             // Sonderangebote insgesamt (abgelaufene bleiben gespeichert)
const SONDER_TAGE_MAX = 366;        // längster Zeitraum
const SONDER_STATUS = ['laeuft' => 'läuft', 'geplant' => 'geplant', 'beendet' => 'beendet', 'abgelaufen' => 'abgelaufen'];

function sonder_ist($def): bool { return is_array($def) && ($def['art'] ?? '') === SONDER_ART; }
/* Kundenangebote ohne Sonderangebote (Obergrenze OFFER_MAX, Preisimport) */
function sonder_ohne(array $offers): array { return array_values(array_filter($offers, function ($o) { return !sonder_ist($o); })); }
/* IDs aller Sonderangebote */
function sonder_ids(): array
{
    $ids = [];
    foreach (offers_load()['offers'] as $o) if (sonder_ist($o)) $ids[] = (string)$o['id'];
    return $ids;
}
function sonder_tz(): DateTimeZone { return new DateTimeZone('Europe/Berlin'); }
function sonder_heute(): string { return (new DateTimeImmutable('now', sonder_tz()))->format('Y-m-d'); }
/* Datum „JJJJ-MM-TT“, das es gibt (2000–2100), sonst null */
function sonder_datum($v): ?string
{
    if (!is_string($v) || !preg_match('/^\d{4}-\d{2}-\d{2}$/', $v)) return null;
    $d = DateTimeImmutable::createFromFormat('!Y-m-d', $v, sonder_tz());
    return $d && $d->format('Y-m-d') === $v && $v >= '2000-01-01' && $v <= '2100-12-31' ? $v : null;
}
/* Gültigkeit als Tage [von, bis] (beide eingeschlossen); Kalenderwoche = Montag bis Sonntag. null = ungültige Angabe */
function sonder_zeitraum($def): ?array
{
    $g = is_array($def) ? ($def['gueltig'] ?? null) : null;
    if (!is_array($g)) return null;
    if (($g['modus'] ?? '') === 'kw') {
        $j = $g['jahr'] ?? null; $w = $g['kw'] ?? null;
        if (!is_int($j) || !is_int($w) || $j < 2000 || $j > 2100 || !kw_gueltig($w, $j)) return null;
        $mo = (new DateTimeImmutable('now', sonder_tz()))->setISODate($j, $w);
        return ['von' => $mo->format('Y-m-d'), 'bis' => $mo->modify('+6 days')->format('Y-m-d')];
    }
    if (($g['modus'] ?? '') !== 'zeitraum') return null;
    $von = sonder_datum($g['von'] ?? null); $bis = sonder_datum($g['bis'] ?? null);
    return $von && $bis && $von <= $bis ? ['von' => $von, 'bis' => $bis] : null;
}
/* Stand an einem Tag (Vorgabe heute): geplant | laeuft | beendet (vorzeitig) | abgelaufen. Ungültige Angaben gelten nie. */
function sonder_status(array $def, ?string $heute = null): string
{
    $z = sonder_zeitraum($def);
    if (!$z) return 'abgelaufen';
    if (!empty($def['beendet'])) return 'beendet';
    $heute = $heute ?? sonder_heute();
    if ($heute < $z['von']) return 'geplant';
    return $heute > $z['bis'] ? 'abgelaufen' : 'laeuft';
}
/* Überschneidet sich die Gültigkeit mit den Tagen von–bis? (Versand: „Angebote dieser Woche“) */
function sonder_ueberschneidet(array $def, string $von, string $bis): bool
{
    $z = sonder_zeitraum($def);
    return $z !== null && $z['von'] <= $bis && $z['bis'] >= $von;
}
/* Gültigkeit als Text: „KW 48/2026 (23.11.–29.11.2026)“ bzw. „17.11.–21.11.2026“ (über den Jahreswechsel mit beiden Jahren) */
function sonder_gueltig_text(array $def): string
{
    $z = sonder_zeitraum($def);
    if (!$z) return 'ungültige Angabe';
    $v = DateTimeImmutable::createFromFormat('!Y-m-d', $z['von']); $b = DateTimeImmutable::createFromFormat('!Y-m-d', $z['bis']);
    $t = ($v->format('Y') === $b->format('Y') ? $v->format('d.m.') : $v->format('d.m.Y')) . '–' . $b->format('d.m.Y');
    $g = $def['gueltig'];
    return ($g['modus'] ?? '') === 'kw' ? 'KW ' . $g['kw'] . '/' . $g['jahr'] . ' (' . $t . ')' : $t;
}
/* Eingabe der Gültigkeit prüfen: {modus: 'zeitraum', von, bis} oder {modus: 'kw', jahr, kw} */
function sonder_gueltig_clean($g): array
{
    if (!is_array($g)) throw new InvalidArgumentException('Bitte die Gültigkeit angeben: Zeitraum oder Kalenderwoche.');
    $zahl = function ($v) { return is_int($v) ? $v : (is_string($v) && ctype_digit($v) && strlen($v) <= 4 ? (int)$v : null); };
    $modus = $g['modus'] ?? '';
    if ($modus === 'kw') {
        $j = $zahl($g['jahr'] ?? null); $w = $zahl($g['kw'] ?? null);
        if ($j === null || $j < 2000 || $j > 2100) throw new InvalidArgumentException('Bitte ein Jahr zwischen 2000 und 2100 angeben.');
        if ($w === null || $w < 1 || $w > 53) throw new InvalidArgumentException('Bitte eine Kalenderwoche zwischen 1 und 53 angeben.');
        if (!kw_gueltig($w, $j)) throw new InvalidArgumentException("Die KW $w/$j gibt es nicht – das Jahr hat nur 52 Kalenderwochen.");
        return ['modus' => 'kw', 'jahr' => $j, 'kw' => $w];
    }
    if ($modus !== 'zeitraum') throw new InvalidArgumentException('Bitte die Gültigkeit angeben: Zeitraum oder Kalenderwoche.');
    $von = sonder_datum($g['von'] ?? null); $bis = sonder_datum($g['bis'] ?? null);
    if (!$von || !$bis) throw new InvalidArgumentException('Bitte Beginn und Ende des Zeitraums als Datum angeben.');
    if ($von > $bis) throw new InvalidArgumentException('Das Ende des Zeitraums liegt vor dem Beginn.');
    $tage = (int)(new DateTimeImmutable($von))->diff(new DateTimeImmutable($bis))->days + 1;
    if ($tage > SONDER_TAGE_MAX) throw new InvalidArgumentException('Der Zeitraum ist zu lang (höchstens ' . SONDER_TAGE_MAX . ' Tage).');
    return ['modus' => 'zeitraum', 'von' => $von, 'bis' => $bis];
}

/* IDs der Angebote mit eigenen Artikeln im veröffentlichten Angebot („veröffentlicht“) – einmal je Anfrage */
function sonder_veroeffentlicht_ids(): array
{
    static $ids = null;
    if ($ids !== null) return $ids;
    $ids = [];
    $pub = store_read('angebot');
    foreach (is_array($pub['items'] ?? null) ? $pub['items'] : [] as $it) {
        foreach (is_array($it['variants'] ?? null) ? $it['variants'] : [] as $k => $v) if (is_array($v) && ($v['status'] ?? '') !== 'hidden') $ids[(string)$k] = true;
    }
    return $ids;
}
/* Kundengruppe → IDs der Sonderangebote, die ihre Kunden heute sehen (läuft, veröffentlicht) – einmal je Anfrage, damit
   customer_offers() in Schleifen über alle Kunden (Versand, Empfängerlisten) nichts neu rechnet */
function sonder_sichtbar_je_gruppe(): array
{
    static $je = null;
    if ($je !== null) return $je;
    $je = [];
    $heute = sonder_heute();
    foreach (offers_load()['offers'] as $o) {
        if (!sonder_ist($o) || sonder_status($o, $heute) !== 'laeuft' || !isset(sonder_veroeffentlicht_ids()[(string)$o['id']])) continue;
        foreach (is_array($o['sonderGruppen'] ?? null) ? $o['sonderGruppen'] : [] as $g) $je[(string)$g][] = (string)$o['id'];
    }
    return $je;
}
/* Sonderangebote, die ein Kunde heute sieht (nur über seine Kundengruppe) */
function sonder_fuer_kunde(array $c): array
{
    $g = (string)($c['gruppe'] ?? '');
    return $g === '' ? [] : (sonder_sichtbar_je_gruppe()[$g] ?? []);
}

/* Kopfdaten eines aufgelösten Sonderangebots (offer_resolve): Gültigkeit statt der Woche des Wochenangebots.
   KW: week/year = KW des Sonderangebots (Kopf, Angebotswoche, Druck wie gewohnt); Zeitraum: gueltigVon/gueltigBis, ohne KW. */
function sonder_meta(array $m, array $def): array
{
    $z = sonder_zeitraum($def);
    $g = $def['gueltig'] ?? [];
    $hinweis = trim((string)($m['meta']['notice'] ?? ''));
    $m['meta']['sonder'] = true;
    if (!$z) return $m;
    if (($g['modus'] ?? '') === 'kw') {
        $m['meta']['week'] = (int)$g['kw'];
        $m['meta']['year'] = (int)$g['jahr'];
        $m['meta']['title'] = ($hinweis !== '' ? $hinweis : 'Angebot') . ' für die KW ' . (int)$g['kw'] . '/' . (int)$g['jahr'];
        return $m;
    }
    $v = DateTimeImmutable::createFromFormat('!Y-m-d', $z['von']); $b = DateTimeImmutable::createFromFormat('!Y-m-d', $z['bis']);
    $m['meta']['week'] = null;
    $m['meta']['year'] = null;
    $m['meta']['gueltigVon'] = $z['von'];
    $m['meta']['gueltigBis'] = $z['bis'];
    $m['meta']['title'] = ($hinweis !== '' ? $hinweis : 'Angebot') . ' vom ' . ($v->format('Y') === $b->format('Y') ? $v->format('d.m.') : $v->format('d.m.Y')) . ' bis ' . $b->format('d.m.Y');
    return $m;
}

/* Artikel eines Angebots mit eigener Artikelliste in einem Modell (wie die Zahl im Editor) */
function sonder_artikel(?array $m, string $id): int
{
    $n = 0;
    foreach (is_array($m['items'] ?? null) ? $m['items'] : [] as $it) {
        $v = $it['variants'][$id] ?? null;
        if (is_array($v) && ($v['status'] ?? '') !== 'hidden') $n++;
    }
    return $n;
}
/* Liste für den Reiter „Sonderangebote“: Zeilen mit Stand und Artikelzahlen, Kundengruppen mit Namen (Stammdaten) und – nur mit
   „kunden.sehen“, wie in Stammdaten → Angebote – der Zahl ihrer Kunden. Keine Preise, keine Kunden. */
function sonder_liste(array $me): array
{
    $d = offers_load();
    $heute = sonder_heute();
    $dr = store_read('entwurf'); $pub = store_read('angebot');
    $mitNamen = may($me, 'stammdaten.sehen') || may($me, 'kunden.sehen') || may($me, 'angebote.verwalten');
    $mitKunden = may($me, 'kunden.sehen');
    $kunden = [];
    if ($mitKunden) foreach (customers_load()['customers'] as $c) { $g = (string)($c['gruppe'] ?? ''); if ($g !== '') $kunden[$g] = ($kunden[$g] ?? 0) + 1; }
    $gruppen = [];
    if ($mitNamen) foreach (kundengruppen_load()['groups'] as $g) {
        $nr = (string)($g['nr'] ?? '');
        if ($nr !== '') $gruppen[] = ['nr' => $nr, 'name' => (string)($g['name'] ?? '')] + ($mitKunden ? ['kunden' => (int)($kunden[$nr] ?? 0)] : []);
    }
    $zeilen = [];
    foreach ($d['offers'] as $o) {
        if (!sonder_ist($o)) continue;
        $z = sonder_zeitraum($o);
        $gr = array_values(array_map('strval', is_array($o['sonderGruppen'] ?? null) ? $o['sonderGruppen'] : []));
        $zeilen[] = ['id' => (string)$o['id'], 'name' => (string)$o['name'], 'gueltig' => $o['gueltig'] ?? null,
                     'von' => $z['von'] ?? null, 'bis' => $z['bis'] ?? null, 'text' => sonder_gueltig_text($o), 'status' => sonder_status($o, $heute),
                     'gruppen' => $gr, 'kunden' => $mitKunden ? array_sum(array_map(function ($g) use ($kunden) { return (int)($kunden[$g] ?? 0); }, $gr)) : null,
                     'artikel' => sonder_artikel($dr ?: $pub, (string)$o['id']), 'veroeffentlicht' => sonder_artikel($pub, (string)$o['id']),
                     'angelegt' => $o['angelegt'] ?? null, 'geaendert' => $o['geaendert'] ?? null, 'beendet' => $o['beendet'] ?? null];
    }
    return ['rev' => (int)$d['rev'], 'heute' => $heute, 'sonder' => $zeilen, 'gruppen' => $gruppen, 'kundenZahl' => $mitKunden, 'max' => SONDER_MAX];
}

/* Neue ID „sonder-<name>“: nie die eines bestehenden oder gelöschten Angebots, nie eine, unter der noch Daten stehen */
function sonder_neue_id(string $name, array $cur): string
{
    $t = mb_strtolower($name);
    $t = strtr($t, ['ä' => 'ae', 'ö' => 'oe', 'ü' => 'ue', 'ß' => 'ss']);
    $t = trim((string)preg_replace('/[^a-z0-9]+/', '-', $t), '-');
    $t = preg_replace('/^sonder(angebot)?-?/', '', $t);
    $basis = SONDER_PRAEFIX . (substr($t, 0, 26) ?: 'angebot');
    $basis = rtrim($basis, '-');
    $ids = array_column($cur['offers'], 'id');
    $gesperrt = array_merge($ids, array_values(array_filter(is_array($cur['geloescht'] ?? null) ? $cur['geloescht'] : [], 'is_string')), angebot_ids_mit_resten($ids), [OFFER_STD]);
    $belegt = array_flip(array_map('strval', $gesperrt));
    $id = $basis; $k = 2;
    while (isset($belegt[$id])) $id = $basis . '-' . $k++;
    return $id;
}
/* Anlegen bzw. ändern (Name, Kundengruppen, Gültigkeit) und vorzeitig beenden/fortsetzen. Eingabe: {rev, id?, name, gruppen,
   gueltig, beendet?}. Rückgabe: [Dokument „angebote“, Zeile, neu?]. Rechte prüft der Aufrufer (GR-103). */
function sonder_speichern(array $me, array $b): array
{
    $name = s($b['name'] ?? null, 80, false);
    if ($name === null || mb_strlen($name) < 2) throw new InvalidArgumentException('Bitte einen Namen angeben (mindestens 2 Zeichen).');
    $gruppen = offer_gruppen_clean($b['gruppen'] ?? [], $name);
    if (!$gruppen) throw new InvalidArgumentException('Ein Sonderangebot gilt immer für Kundengruppen – bitte mindestens eine wählen.');
    $gueltig = sonder_gueltig_clean($b['gueltig'] ?? null);
    $id = is_string($b['id'] ?? null) ? $b['id'] : '';
    [$out, $row, $neu, $d] = with_lock('angebote', function () use ($me, $b, $name, $gruppen, $gueltig, $id) {
        $cur = offers_load();
        if ((int)($b['rev'] ?? -1) !== (int)$cur['rev']) fail('Die Angebote wurden inzwischen an anderer Stelle geändert. Bitte die Liste neu laden.', 409);
        $offers = $cur['offers'];
        $idx = null;
        if ($id !== '') {
            foreach ($offers as $i => $o) if ((string)$o['id'] === $id) $idx = $i;
            if ($idx === null || !sonder_ist($offers[$idx])) fail('Dieses Sonderangebot gibt es nicht (mehr).', 404);
        }
        $key = mb_strtolower($name);
        if ($key === 'wochenangebot') throw new InvalidArgumentException("Der Name „{$name}“ ist bereits vergeben.");
        foreach ($offers as $i => $o) if ($i !== $idx && mb_strtolower((string)$o['name']) === $key) throw new InvalidArgumentException("Der Name „{$name}“ ist bereits vergeben.");
        $alt = $idx !== null && is_array($offers[$idx]['sonderGruppen'] ?? null) ? array_map('strval', $offers[$idx]['sonderGruppen']) : [];
        $known = array_map('strval', array_column(kundengruppen_load()['groups'], 'nr'));
        foreach (array_diff($gruppen, $alt) as $g) if (!in_array($g, $known, true)) throw new InvalidArgumentException("Die Kundengruppe $g gibt es nicht. Bitte unter Stammdaten → Kundengruppen anlegen.");
        $z = sonder_zeitraum(['gueltig' => $gueltig]);
        $wer = ['t' => now(), 'von' => (string)$me['name']];
        $text = function (array $g) { return sonder_gueltig_text(['gueltig' => $g]); };
        $d = [];
        if ($idx === null) {
            if (count($offers) - count(sonder_ohne($offers)) >= SONDER_MAX) throw new InvalidArgumentException('Höchstens ' . SONDER_MAX . ' Sonderangebote – bitte abgelaufene löschen.');
            if ($z['bis'] < sonder_heute()) throw new InvalidArgumentException('Das Ende der Gültigkeit liegt in der Vergangenheit.');
            $row = ['id' => sonder_neue_id($name, $cur), 'name' => $name, 'fallback' => 'hidden', 'art' => SONDER_ART, 'gueltig' => $gueltig,
                    'sonderGruppen' => $gruppen, 'angelegt' => $wer];
            $offers[] = $row;
            $oid = $row['id'];
            $d[] = ['k' => "o$oid|+", 'code' => '', 'name' => $name, 'f' => 'Neues Sonderangebot', 'from' => '', 'to' => $text($gueltig)];
            $d[] = ['k' => "o$oid|grp", 'code' => '', 'name' => $name, 'f' => 'Kundengruppen', 'from' => '', 'to' => implode(', ', $gruppen)];
        } else {
            $old = $offers[$idx];
            $oid = (string)$old['id'];
            // Felder, die dieser Stand nicht kennt (neuere Fassung), bleiben erhalten (GR-006); „gruppen“ gibt es bei Sonderangeboten nie
            $row = ['id' => $oid, 'name' => $name, 'fallback' => 'hidden', 'art' => SONDER_ART, 'gueltig' => $gueltig, 'sonderGruppen' => $gruppen]
                 + array_diff_key($old, array_flip(['id', 'name', 'fallback', 'art', 'gueltig', 'sonderGruppen', 'gruppen', 'beendet', 'geaendert']));
            $ende = array_key_exists('beendet', $b) ? !empty($b['beendet']) : !empty($old['beendet']);
            if ($ende) $row['beendet'] = is_array($old['beendet'] ?? null) ? $old['beendet'] : $wer;
            $row['geaendert'] = $wer;
            if ((string)$old['name'] !== $name) $d[] = ['k' => "o$oid|name", 'code' => '', 'name' => $name, 'f' => 'Name', 'from' => (string)$old['name'], 'to' => $name];
            $altG = is_array($old['gueltig'] ?? null) ? $old['gueltig'] : [];
            if ($altG !== $gueltig) $d[] = ['k' => "o$oid|gueltig", 'code' => '', 'name' => $name, 'f' => 'Gültigkeit', 'from' => $altG ? $text($altG) : '', 'to' => $text($gueltig)];
            if ($alt !== $gruppen) $d[] = ['k' => "o$oid|grp", 'code' => '', 'name' => $name, 'f' => 'Kundengruppen', 'from' => implode(', ', $alt), 'to' => implode(', ', $gruppen)];
            if (empty($old['beendet']) !== !$ende) $d[] = ['k' => "o$oid|ende", 'code' => '', 'name' => $name, 'f' => 'Vorzeitig beendet', 'from' => empty($old['beendet']) ? 'nein' : 'ja', 'to' => $ende ? 'ja' : 'nein'];
            $offers[$idx] = $row;
        }
        $out = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => (string)$me['name'], 'offers' => array_values($offers)]
             + array_diff_key($cur, array_flip(['rev', 'updatedAt', 'updatedBy', 'offers']));   // weitere Felder bleiben (GR-006)
        store_write('angebote', $out);
        return [$out, $row, $idx === null, $d];
    });
    if ($d) audit('offers', ($neu ? 'Sonderangebot angelegt: ' : 'Sonderangebot geändert: ') . $name, $d);
    return [$out, $row, $neu];
}
/* Löschen (Eingabe {rev, id}). Die ID wird nie wieder vergeben (geloescht), Preise im Entwurf fallen beim nächsten Speichern weg.
   Rechte und Bestätigung prüft der Aufrufer. */
function sonder_loeschen(array $me, array $b): array
{
    $id = is_string($b['id'] ?? null) ? $b['id'] : '';
    [$out, $name] = with_lock('angebote', function () use ($me, $b, $id) {
        $cur = offers_load();
        if ((int)($b['rev'] ?? -1) !== (int)$cur['rev']) fail('Die Angebote wurden inzwischen an anderer Stelle geändert. Bitte die Liste neu laden.', 409);
        $offers = $cur['offers'];
        $idx = null;
        foreach ($offers as $i => $o) if ((string)$o['id'] === $id) $idx = $i;
        if ($idx === null || !sonder_ist($offers[$idx])) fail('Dieses Sonderangebot gibt es nicht (mehr).', 404);
        $name = (string)$offers[$idx]['name'];
        array_splice($offers, $idx, 1);
        $geloescht = array_values(array_unique(array_merge(array_values(array_filter(is_array($cur['geloescht'] ?? null) ? $cur['geloescht'] : [], 'is_string')), [$id])));
        $out = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => (string)$me['name'], 'offers' => array_values($offers), 'geloescht' => array_slice($geloescht, -2000)]
             + array_diff_key($cur, array_flip(['rev', 'updatedAt', 'updatedBy', 'offers', 'geloescht']));
        store_write('angebote', $out);
        return [$out, $name];
    });
    audit('offers', 'Sonderangebot gelöscht: ' . $name, [['k' => "o$id|-", 'code' => '', 'name' => $name, 'f' => 'Sonderangebot gelöscht', 'from' => $name, 'to' => '']]);
    return $out;
}
