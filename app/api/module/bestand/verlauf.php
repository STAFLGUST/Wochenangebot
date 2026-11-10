<?php
declare(strict_types=1);
/* Modul Bestand · Bestandsverlauf (Auftrag des Inhabers 02.11.2026): bei jedem Übernehmen der Bestandsliste (Bestand →
   Bestandsliste hochladen, Aktion stock_import, Importzentrale) wird ein Tagesstand gespeichert – je Artikel kg eingelagert,
   erwartete Zugänge (Status „erfasst“), Lagerwert zum EK, kg mit EK, Partien und Bezeichnung (Schnappschuss, GR-106).
   Dokumente: BESTAND_VERLAUF (Verzeichnis: Summen je Tag und Herkunft) und BESTAND_VERLAUF/<JJJJ-MM-TT> (je Artikel).
   Erneutes Übernehmen für denselben Tag ersetzt den Tagesstand; frühere Tage bleiben. Der Verlauf wird nie angezeigt, außer
   über die Schnittstelle unten: das Controlling (Bereich Bestandsverlauf) liest ihn nur über bestand_verlauf_index() und
   bestand_verlauf_tag() (regeln/datenverantwortung.toml) und gibt Lagerwerte nur mit controlling.bestand_ek und
   bestand.einkaufspreise aus (GR-008). Geladen von module/bestand/import.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const BESTAND_VERLAUF = 'bestand-verlauf';
/* Felder je Artikel im Tagesstand (Liste statt Objekt, damit ein Jahr klein bleibt) */
const BESTAND_VERLAUF_FELDER = ['kg', 'zugang', 'ekWert', 'ekKg', 'partien'];

/* Tagesstand aus der übernommenen Bestandsliste: artikel[code] = [kg, zugang, ekWert, ekKg, partien], namen[code] */
function bestand_verlauf_stand(array $articles, array $incoming): array
{
    $art = []; $namen = [];
    foreach ($articles as $a) {
        $code = (string)$a['code'];
        $ekWert = 0.0; $ekKg = 0.0;
        foreach ($a['lots'] ?? [] as $l) {
            if (!isset($l['ek']) || $l['ek'] === null || (float)$l['ek'] <= 0) continue;   // ohne Einkaufspreis (auch 0 aus älteren Listen)
            $ekWert += (float)$l['kg'] * (float)$l['ek'];
            $ekKg += (float)$l['kg'];
        }
        $art[$code] = [round((float)$a['kg'], 3), 0.0, round($ekWert, 2), round($ekKg, 3), count($a['lots'] ?? [])];
        $namen[$code] = (string)($a['name'] ?? '');
    }
    foreach ($incoming as $z) {
        $code = (string)$z['code'];
        if (!isset($art[$code])) { $art[$code] = [0.0, 0.0, 0.0, 0.0, 0]; $namen[$code] = (string)($z['name'] ?? ''); }
        $art[$code][1] = round($art[$code][1] + (float)$z['kg'], 3);
    }
    ksort($art, SORT_NATURAL);
    return ['felder' => BESTAND_VERLAUF_FELDER, 'artikel' => $art, 'namen' => $namen];
}

/* Summen eines Tagesstands für das Verzeichnis */
function bestand_verlauf_summen(array $stand): array
{
    $s = ['kg' => 0.0, 'zugang' => 0.0, 'ekWert' => 0.0, 'ekKg' => 0.0, 'artikel' => 0, 'partien' => 0];
    foreach ($stand['artikel'] as $w) {
        $s['kg'] += $w[0]; $s['zugang'] += $w[1]; $s['ekWert'] += $w[2]; $s['ekKg'] += $w[3]; $s['partien'] += $w[4];
        if ($w[0] > 0) $s['artikel']++;
    }
    foreach (['kg' => 3, 'zugang' => 3, 'ekWert' => 2, 'ekKg' => 3] as $k => $n) $s[$k] = round($s[$k], $n);
    return $s;
}

/* Tagesstand speichern (ersetzt einen früheren desselben Tags); ohne gültiges Datum: heute */
function bestand_verlauf_schreiben(?string $datum, array $articles, array $incoming, string $quelle, array $me): array
{
    $datum = $datum !== null && preg_match('/^\d{4}-\d{2}-\d{2}$/', $datum) ? $datum : date('Y-m-d');
    $stand = bestand_verlauf_stand($articles, $incoming);
    $kopf = ['datum' => $datum, 'quelle' => $quelle, 'um' => now(), 'von' => (string)($me['name'] ?? '')];
    return with_lock(BESTAND_VERLAUF, function () use ($datum, $stand, $kopf) {
        store_write(BESTAND_VERLAUF . '/' . $datum, $kopf + $stand);
        $ix = store_read(BESTAND_VERLAUF);
        $tage = is_array($ix['tage'] ?? null) ? $ix['tage'] : [];
        $tage[$datum] = bestand_verlauf_summen($stand) + ['quelle' => $kopf['quelle'], 'um' => $kopf['um'], 'von' => $kopf['von']];
        ksort($tage);
        store_write(BESTAND_VERLAUF, ['v' => 1, 'tage' => $tage]);
        return $tage[$datum];
    });
}

/* ---------- Schnittstelle für das Controlling (nur lesen; enthält Lagerwerte zum EK – der Aufrufer prüft die Rechte) ---------- */

/* Verzeichnis: Datum => Summen (kg, zugang, ekWert, ekKg, artikel, partien) und Herkunft (quelle, um, von), aufsteigend */
function bestand_verlauf_index(): array
{
    $ix = store_read(BESTAND_VERLAUF);
    return is_array($ix['tage'] ?? null) ? $ix['tage'] : [];
}

/* Tagesstand eines Tags oder null: datum, quelle, um, von, felder, artikel[code] = [kg, zugang, ekWert, ekKg, partien], namen */
function bestand_verlauf_tag(string $datum): ?array
{
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $datum)) return null;
    $d = store_read(BESTAND_VERLAUF . '/' . $datum);
    return is_array($d) && is_array($d['artikel'] ?? null) ? $d : null;
}
