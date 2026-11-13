<?php
declare(strict_types=1);
/* Druck der Angebote: Fußzeile des Briefbogens unter jedem gedruckten Angebot (Wunsch des Inhabers 13.11.2026).
   Die Fußzeile besteht aus drei Textspalten (Firma/Anschrift · Telefon/Web · Bank/Steuer) und zwei Zeilen (Handelsregister);
   davor stehen die Siegel (assets/druck-siegel.jpg), darüber der Hinweis zu Mengen und Fracht (lib/fracht.php).
   Gespeichert als optionales Feld „druck“ im Dokument „fracht“ (Einstellungen des Angebots; ältere Fassungen ohne das Feld
   bleiben lesbar, fracht_save erhält es): {spalten: [3 Texte], zeilen: [2 Texte], modus: 'jede'|'letzte', bankGeschuetzt: bool}.
   Ohne eigene Angaben gilt die Vorgabe unten – nur was ohnehin öffentlich im Impressum der Angebotsseite steht; Bank-,
   Steuer- und weitere Registerangaben trägt ein Administrator ein (Angebot bearbeiten → ⋯ → „Fußzeile im Druck“), sie
   stehen nicht im Code (GR-007). Ausgeliefert wird die Fußzeile mit dem Angebot (fracht_public → „fuss“), weil jede
   Druckfassung sie zeigt – sie enthält nur Angaben des Geschäftsbriefs.
   bankGeschuetzt (Vorgabe: an): die dritte Spalte (Bank und Steuer) geht nur an angemeldete Nutzer – Mitarbeiter und
   Kunden mit eigenem Passwort (druck_angemeldet). Ohne Anmeldung, also im öffentlichen Wochenangebot, steht dort nur die
   Vorgabe aus dem Impressum; entschieden wird hier auf dem Server, nicht im Browser (GR-103).
   modus: Fußzeile und Hinweis auf jeder Seite („jede“) oder nur am Fuß der letzten Seite („letzte“).
   Dieselbe Fußzeile setzt druck_fuss_pdf() unter das PDF des Einzelangebots (lib/einzelangebote.php, E-Mail-Anhang). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const DRUCK_FUSS_MODI = ['jede', 'letzte'];
const DRUCK_FUSS_MODUS = 'letzte';   // Vorgabe (Inhaber 13.11.2026): Fußzeile und Hinweis nur am Ende, auf der letzten Seite
const DRUCK_FUSS_ZEILEN = 6;       // Zeilen je Spalte
const DRUCK_FUSS_LAENGE = 70;      // Zeichen je Zeile einer Spalte
const DRUCK_FUSS_LANG = 200;       // Zeichen je Registerzeile
/* Vorgabe: Angaben aus dem Impressum (app/impressum/) und dem Hinweis der Frachtregel – nichts darüber hinaus */
const DRUCK_FUSS_VORGABE = [
    'spalten' => [
        "Standard-Fleisch GmbH & Co. KG\nLagerstraße 17\n20357 Hamburg",
        "Telefon ( 040 ) 43 25 88-0\nTelefax ( 040 ) 43 25 88-88\nwww.standard-fleisch.de\ninfo@standard-fleisch.de",
        "Ust-IdNr. : DE 118949959",
    ],
    'zeilen' => [
        'Eingetragen Handelsregister Hamburg B 522 68 * Geschäftsführer : Jan Lawrence, Markus Nachtigall, Nils Dwenger, Tilman Paschen',
        'Eingetragen Handelsregister Hamburg A 828 28 * Persönlich haftende Gesellschafterin : Jan Lawrence Handelsgesellschaft mbH',
    ],
];

/* Text einer Spalte: höchstens DRUCK_FUSS_ZEILEN Zeilen, ohne Steuerzeichen, Leerzeichen bereinigt */
function druck_fuss_text($v, int $zeilen, int $laenge): string
{
    $t = is_string($v) ? $v : '';
    $t = str_replace("\r", '', preg_replace('/[\x00-\x09\x0b-\x1f\x7f]/u', ' ', $t) ?? '');
    $out = [];
    foreach (explode("\n", $t) as $l) {
        $l = trim(preg_replace('/\s+/u', ' ', $l) ?? '');
        if ($l !== '') $out[] = mb_substr($l, 0, $laenge);
    }
    return implode("\n", array_slice($out, 0, $zeilen));
}
/* Eingabe prüfen: drei Spalten, zwei Zeilen, Modus – unbekannte Felder fallen weg */
function druck_fuss_clean($in): array
{
    $in = is_array($in) ? $in : [];
    $sp = is_array($in['spalten'] ?? null) ? array_values($in['spalten']) : [];
    $ze = is_array($in['zeilen'] ?? null) ? array_values($in['zeilen']) : [];
    $spalten = []; $zeilen = [];
    for ($i = 0; $i < 3; $i++) $spalten[] = druck_fuss_text($sp[$i] ?? '', DRUCK_FUSS_ZEILEN, DRUCK_FUSS_LAENGE);
    for ($i = 0; $i < 2; $i++) $zeilen[] = druck_fuss_text($ze[$i] ?? '', 1, DRUCK_FUSS_LANG);
    $modus = in_array($in['modus'] ?? '', DRUCK_FUSS_MODI, true) ? $in['modus'] : DRUCK_FUSS_MODUS;
    $bank = !array_key_exists('bankGeschuetzt', $in) || !empty($in['bankGeschuetzt']);   // ohne Angabe geschützt (sichere Vorgabe)
    return ['spalten' => $spalten, 'zeilen' => $zeilen, 'modus' => $modus, 'bankGeschuetzt' => $bank];
}
/* Gespeicherte Einstellung (roh) oder null */
function druck_fuss_gespeichert(): ?array
{
    $d = store_read('fracht');
    return is_array($d) && is_array($d['druck'] ?? null) ? $d['druck'] : null;
}
/* Wirksame Fußzeile: eigene Texte, sonst die Vorgabe; „eigen“ sagt, ob Texte hinterlegt sind */
function druck_fuss(): array
{
    $g = druck_fuss_gespeichert();
    $c = druck_fuss_clean($g ?? []);
    $eigen = implode('', $c['spalten']) . implode('', $c['zeilen']) !== '';
    if (!$eigen) { $c['spalten'] = DRUCK_FUSS_VORGABE['spalten']; $c['zeilen'] = DRUCK_FUSS_VORGABE['zeilen']; }
    return $c + ['eigen' => $eigen, 'updatedAt' => $g['updatedAt'] ?? null, 'updatedBy' => (string)($g['updatedBy'] ?? '')];
}
/* Angemeldet im Sinne der Fußzeile: Mitarbeiter oder Kunde mit eigenem Passwort. Ohne Sitzungs-Cookie wird keine Sitzung
   begonnen – das öffentliche Wochenangebot bleibt ohne Cookie abrufbar. */
function druck_angemeldet(): bool
{
    if (function_exists('oidc_modus') && oidc_modus()) return current_user() !== null;
    if (!app_client() && !isset($_COOKIE[sitzung_cookie_name()])) return false;
    if (current_user()) return true;
    $k = current_customer();
    return $k !== null && empty($k['login']['mustChange']);
}
/* Für die Angebotsseite (Druck): nur Texte und Modus. Geschützte Bankangaben (dritte Spalte) nur für angemeldete Nutzer –
   sonst steht dort die Vorgabe aus dem Impressum. */
function druck_fuss_public(bool $angemeldet = false): array
{
    $f = druck_fuss();
    if ($f['eigen'] && $f['bankGeschuetzt'] && !$angemeldet) $f['spalten'][2] = DRUCK_FUSS_VORGABE['spalten'][2];
    return ['spalten' => $f['spalten'], 'zeilen' => $f['zeilen'], 'modus' => $f['modus']];
}
/* Speichern (nur das Feld „druck“; Fracht und Hinweis bleiben unverändert). Leere Texte = wieder die Vorgabe. */
function druck_fuss_speichern($in, array $me): array
{
    $alt = druck_fuss();
    $neu = druck_fuss_clean($in);
    with_lock('fracht', function () use ($neu, $me) {
        $d = store_read('fracht');
        if (!is_array($d)) $d = ['aktiv' => FRACHT_DEFAULT['aktiv'], 'staffeln' => FRACHT_DEFAULT['staffeln'], 'zusatz' => FRACHT_DEFAULT['zusatz']];
        $d['druck'] = $neu + ['updatedAt' => now(), 'updatedBy' => $me['name']];
        store_write('fracht', $d);
    });
    $jetzt = druck_fuss();
    $ch = [];
    foreach ([0 => 'Spalte 1', 1 => 'Spalte 2', 2 => 'Spalte 3'] as $i => $n) {
        if ($alt['spalten'][$i] !== $jetzt['spalten'][$i]) $ch[] = ['k' => "druck|s$i", 'code' => '', 'name' => 'Fußzeile im Druck', 'f' => $n, 'from' => str_replace("\n", ' / ', $alt['spalten'][$i]), 'to' => str_replace("\n", ' / ', $jetzt['spalten'][$i])];
    }
    foreach ([0 => 'Zeile 1', 1 => 'Zeile 2'] as $i => $n) {
        if ($alt['zeilen'][$i] !== $jetzt['zeilen'][$i]) $ch[] = ['k' => "druck|z$i", 'code' => '', 'name' => 'Fußzeile im Druck', 'f' => $n, 'from' => $alt['zeilen'][$i], 'to' => $jetzt['zeilen'][$i]];
    }
    $mt = ['jede' => 'auf jeder Seite', 'letzte' => 'nur auf der letzten Seite'];
    if ($alt['modus'] !== $jetzt['modus']) $ch[] = ['k' => 'druck|modus', 'code' => '', 'name' => 'Fußzeile im Druck', 'f' => 'Fußzeile und Hinweis', 'from' => $mt[$alt['modus']], 'to' => $mt[$jetzt['modus']]];
    if ($alt['bankGeschuetzt'] !== $jetzt['bankGeschuetzt']) $ch[] = ['k' => 'druck|bank', 'code' => '', 'name' => 'Fußzeile im Druck', 'f' => 'Bankangaben nur für angemeldete Nutzer', 'from' => $alt['bankGeschuetzt'] ? 'ja' : 'nein', 'to' => $jetzt['bankGeschuetzt'] ? 'ja' : 'nein'];
    if ($ch) audit('mail', 'Fußzeile im Druck der Angebote geändert', $ch);
    return $jetzt;
}

/* ---------- Fußzeile im PDF des Einzelangebots (lib/pdf.php) ----------
   Dieselben Texte wie im Druck der Angebotsseite: dünne Linie, Siegel links, drei Spalten, rechts die Registerzeilen – über
   die ganze Breite. Das PDF geht an den Kunden des Angebots bzw. an Mitarbeiter (Vorschau): vollständige Angaben. */
const DRUCK_FUSS_PDF = ['schrift' => 6.6, 'zeile' => 8.1, 'siegel' => 40.0, 'oben' => 6.0];   // pt
/* Höhe der Fußzeile in pt (0 = keine) */
function druck_fuss_pdf_hoehe(array $f): float
{
    $n = 0;
    foreach ($f['spalten'] as $t) $n = max($n, $t === '' ? 0 : count(explode("\n", $t)));
    $z = count(array_filter($f['zeilen'], fn($x) => $x !== ''));
    if (!$n && !$z) return 0.0;
    return DRUCK_FUSS_PDF['oben'] + max(DRUCK_FUSS_PDF['siegel'], max($n, $z * 2) * DRUCK_FUSS_PDF['zeile']) + 2;
}
/* Fußzeile zeichnen: $x linker Rand, $y Oberkante (Linie), $w Breite */
function druck_fuss_pdf(Pdf $pdf, array $f, float $x, float $y, float $w): void
{
    $M = DRUCK_FUSS_PDF; $fs = $M['schrift']; $lh = $M['zeile'];
    $spalten = array_values(array_filter(array_map(fn($t) => $t === '' ? [] : explode("\n", $t), $f['spalten'])));
    $zeilen = array_values(array_filter($f['zeilen'], fn($z) => $z !== ''));
    if (!$spalten && !$zeilen) return;
    $pdf->line($x, $y, $x + $w, $y, .7, '#111111');
    $oben = $y + $M['oben'];
    $siegel = dirname(__DIR__, 3) . '/assets/druck-siegel.jpg';
    $sw = is_file($siegel) ? $M['siegel'] * 316 / 250 : 0.0;
    if ($sw > 0) $pdf->jpeg($siegel, $x, $oben, $sw);
    // Breiten: Spalten so breit wie ihr längster Text, Registerzeilen bekommen den Rest (umbrochen)
    $bw = array_map(fn($l) => max(array_map(fn($t) => Pdf::width($t, $fs), $l)), $spalten);
    $rest = $w - $sw - array_sum($bw);
    $bloecke = count($spalten) + ($zeilen ? 1 : 0);
    $zw = $zeilen ? max(120.0, min(232.0, $rest - 14.0 * $bloecke)) : 0.0;
    $zl = [];
    foreach ($zeilen as $z) { foreach (Pdf::wrap($z, $fs, $zw) as $l) $zl[] = $l; }
    $zb = $zl ? max(array_map(fn($t) => Pdf::width($t, $fs), $zl)) : 0.0;
    $luecke = $bloecke > 0 ? max(8.0, ($w - $sw - array_sum($bw) - $zb) / $bloecke) : 0.0;
    $hoehe = max($M['siegel'], max(array_merge([0], array_map('count', $spalten), [count($zl)])) * $lh);
    $cx = $x + $sw + $luecke;
    foreach ($spalten as $i => $l) {
        $ty = $oben + ($hoehe - count($l) * $lh) / 2 + $fs;   // senkrecht mittig zum Siegel
        foreach ($l as $j => $t) $pdf->text($cx, $ty + $j * $lh, $t, $fs);
        $cx += $bw[$i] + $luecke;
    }
    if ($zl) {
        $zx = $x + $w - $zb;
        $ty = $oben + ($hoehe - count($zl) * $lh) / 2 + $fs;
        foreach ($zl as $j => $t) $pdf->text($zx, $ty + $j * $lh, $t, $fs);
    }
}
