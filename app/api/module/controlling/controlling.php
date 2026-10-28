<?php
declare(strict_types=1);
/* Modul Controlling · gemeinsame Grundlage aller Bereiche (Umsatzstatistik; geplant: OP-Konten, Liquidität und weitere).
   Jeder Bereich hat eigene Rechte „controlling.<bereich>_sehen/_bearbeiten“, eigene Dokumente „controlling-<bereich>“ und
   eigene Aktionen „controlling_<bereich>_…“ – ein neuer Bereich kommt als eigene Datei in diesem Ordner dazu und wird in
   CONTROLLING_BEREICHE eingetragen; bestehende Bereiche und ihre Daten bleiben unberührt.
   Finanzdaten sind vertraulich: Modulzugang standardmäßig für niemanden (Register zugang_rollen = []), jeder Bereich
   braucht sein eigenes Recht (GR-103). Ursprung der Umsatzstatistik: Modul „Gust 1“ aus dem Modulbausatz (28.10.2026). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Bereiche in Anzeigereihenfolge: Kennung => Name, Recht zum Ansehen, Recht zum Bearbeiten (oder null) */
const CONTROLLING_BEREICHE = [
    'umsatz' => ['name' => 'Umsatzstatistik', 'sehen' => 'controlling.umsatz_sehen', 'bearbeiten' => 'controlling.umsatz_bearbeiten'],
];

const CONTROLLING_MONATE = ['01' => 'Januar', '02' => 'Februar', '03' => 'März', '04' => 'April', '05' => 'Mai', '06' => 'Juni',
                            '07' => 'Juli', '08' => 'August', '09' => 'September', '10' => 'Oktober', '11' => 'November', '12' => 'Dezember'];

/* Bereiche, die dieser Mitarbeiter sehen darf, mit Bearbeitungsrecht (nur Anzeigehilfe – jede Aktion prüft selbst) */
function controlling_bereiche(array $me): array
{
    $out = [];
    foreach (CONTROLLING_BEREICHE as $id => $b) {
        if (!may($me, $b['sehen'])) continue;
        $out[] = ['id' => $id, 'name' => $b['name'], 'bearbeiten' => $b['bearbeiten'] !== null && may($me, $b['bearbeiten'])];
    }
    return $out;
}

/* Jahr aus der Anfrage (2000–2100) als Text „JJJJ“ */
function controlling_jahr($v): string
{
    $j = filter_var($v, FILTER_VALIDATE_INT);
    if ($j === false || $j < 2000 || $j > 2100) throw new InvalidArgumentException('Bitte ein Jahr zwischen 2000 und 2100 angeben.');
    return (string)$j;
}

/* Monat „01“–„12“ (auch 1–12 als Zahl) */
function controlling_monat($v): string
{
    $m = is_int($v) || (is_string($v) && preg_match('/^\d{1,2}$/', $v)) ? sprintf('%02d', (int)$v) : '';
    if (!isset(CONTROLLING_MONATE[$m])) throw new InvalidArgumentException('Bitte einen gültigen Monat auswählen.');
    return $m;
}

/* Betrag oder Menge: Zahl oder leer (null); $negativ: negative Werte erlaubt (z. B. Deckungsbeitrag) */
function controlling_zahl($wert, int $nachkomma, bool $negativ, string $was): ?float
{
    if ($wert === null || $wert === '') return null;
    if (!is_int($wert) && !is_float($wert) && !(is_string($wert) && is_numeric($wert))) throw new InvalidArgumentException("$was: bitte nur Zahlen oder ein leeres Feld.");
    $z = (float)$wert;
    if (!is_finite($z) || abs($z) > 1e12) throw new InvalidArgumentException("$was: Zahl ungültig oder zu groß.");
    if (!$negativ && $z < 0) throw new InvalidArgumentException("$was darf nicht negativ sein.");
    return round($z, $nachkomma);
}
