<?php
declare(strict_types=1);
/* QM-System · Verfahrensdokumentation: Export als PDF bzw. ZIP (Aktion qs_verfahren_export, nur lesen).

   Drei Arten:
     - eine Fassung (fassung=N)            → PDF dieser Fassung
     - der Arbeitsstand (fassung=0)        → PDF, auf jeder Seite als ENTWURF gekennzeichnet (nicht freigegeben)
     - Export für Prüfungen (von, bis)     → PDF mit Deckblatt, Übersicht ALLER Fassungen (gültig von/bis, Freigabe, Anlass,
       Änderungen = nachvollziehbare Änderungshistorie, GoBD Rz. 154) und dem vollen Inhalt jeder Fassung, die im Zeitraum
       galt. Das PDF einer einzelnen Fassung nennt die Historie nur bis zu dieser Fassung. Mit dokumente=1 als ZIP: dazu die Dateien der verknüpften QM-Dokumente in der Version, die die jeweilige
       Fassung festgehalten hat (aus der Dokumentenablage, lib/dateiablage.php).
   Der Inhalt kommt immer aus dem gespeicherten Schnappschuss der Fassung (GR-106) – nie aus dem heutigen Stand der
   QM-Dokumente oder Personen. PDF über lib/pdf.php (Helvetica, WinAnsi); zwei Durchläufe für „Seite x von y“. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar
require_once __DIR__ . '/../../lib/pdf.php';

/* Fließsatz auf A4 hoch: Absätze mit Umbruch, Seitenwechsel, Fußzeile */
final class QsVfSatz
{
    public const L = 56.0;
    public const R = 539.0;
    private const OBEN = 62.0;
    private const UNTEN = 778.0;
    public Pdf $pdf;
    public float $y = self::OBEN;
    private int $seite = 1;

    public function __construct(private string $fuss, private int $gesamt, private string $marke = '')
    {
        $this->pdf = new Pdf(595.28, 841.89);
        $this->rahmen();
    }
    private function rahmen(): void
    {
        $this->pdf->line(self::L, 800, self::R, 800, .5, '#b9b4ac');
        $this->pdf->text(self::L, 813, $this->fuss, 7.5, false, '#5f5b55');
        $this->pdf->text(self::R, 813, 'Seite ' . $this->seite . ($this->gesamt ? ' von ' . $this->gesamt : ''), 7.5, false, '#5f5b55', 'r');
        if ($this->marke !== '') $this->pdf->text(self::R, 40, $this->marke, 9, true, '#b3261e', 'r');
    }
    public function seiten(): int { return $this->seite; }
    public function neueSeite(): void { $this->pdf->addPage(); $this->seite++; $this->y = self::OBEN; $this->rahmen(); }
    /* Platz für $h Punkt sichern (sonst neue Seite) */
    public function platz(float $h): void { if ($this->y + $h > self::UNTEN) $this->neueSeite(); }
    public function abstand(float $h): void { $this->y += $h; }
    public function linie(): void { $this->pdf->line(self::L, $this->y, self::R, $this->y, .5, '#b9b4ac'); $this->y += 8; }
    /* Text mit Zeilenumbrüchen und Umbruch nach Wörtern; $einzug in Punkt, $vor = Zeichen vor der ersten Zeile (z. B. „•“) */
    public function text(string $t, float $size = 9.5, bool $bold = false, string $farbe = '#1b1a18', float $einzug = 0, string $vor = ''): void
    {
        $zeile = $size * 1.42;
        $erste = true;
        foreach (explode("\n", str_replace("\r", '', $t)) as $absatz) {
            if (trim($absatz) === '') { $this->y += $zeile * .6; continue; }
            foreach (Pdf::wrap($absatz, $size, self::R - self::L - $einzug, $bold) as $z) {
                $this->platz($zeile);
                $this->y += $zeile;
                if ($erste && $vor !== '') $this->pdf->text(self::L + $einzug - 9, $this->y - $zeile * .28, $vor, $size, false, $farbe);
                $this->pdf->text(self::L + $einzug, $this->y - $zeile * .28, $z, $size, $bold, $farbe);
                $erste = false;
            }
        }
    }
    /* „Bezeichnung   Wert“ (Wert mit Umbruch); leere Werte werden ausgelassen */
    public function paar(string $k, string $v): void
    {
        if (trim($v) === '') return;
        $this->platz(13.5);
        $this->pdf->text(self::L, $this->y + 13.5 - 3.8, $k, 8.5, false, '#5f5b55');
        $this->text($v, 9.5, false, '#1b1a18', 132);
    }
}

function qs_vf_pdf_name(array $inhalt, string $kuerzel): string
{
    return $kuerzel === '' ? '' : (isset($inhalt['personen'][$kuerzel]) ? $kuerzel . ' (' . $inhalt['personen'][$kuerzel] . ')' : $kuerzel);
}
function qs_vf_pdf_gueltig(string $ab, string $bis): string
{
    return 'gültig ab ' . qs_de($ab) . ($bis !== '' ? ' bis ' . qs_de($bis) : '');
}
/* Inhalt einer Fassung (oder des Arbeitsstands) setzen */
function qs_vf_pdf_inhalt(QsVfSatz $s, array $inhalt): void
{
    $sysName = []; foreach ($inhalt['systeme'] ?? [] as $x) $sysName[(string)$x['id']] = (string)$x['name'];
    $rang = 0;
    foreach (QS_VF_TEILE as $teil => $titel) {
        $rang++;
        $liste = array_values(array_filter($inhalt['abschnitte'] ?? [], function ($a) use ($teil) { return ($a['teil'] ?? '') === $teil; }));
        if (!$liste) continue;
        $s->platz(90);
        $s->abstand(10);
        $s->text($rang . ' ' . $titel, 13, true);
        $s->abstand(3);
        $s->linie();
        foreach ($liste as $a) {
            $s->platz(58);
            $s->abstand(4);
            $s->text($a['nr'] . ' ' . $a['titel'], 10.5, true);
            $meta = [];
            if (($a['zustaendig'] ?? '') !== '') $meta[] = 'Zuständig: ' . qs_vf_pdf_name($inhalt, (string)$a['zustaendig']);
            $namen = array_values(array_filter(array_map(function ($id) use ($sysName) { return $sysName[(string)$id] ?? ''; }, $a['systeme'] ?? [])));
            if ($namen) $meta[] = 'IT-Systeme: ' . implode(', ', $namen);
            if ($meta) $s->text(implode(' · ', $meta), 8.5, false, '#5f5b55');
            if (($a['text'] ?? '') !== '') { $s->abstand(2); $s->text((string)$a['text']); }
            if (!empty($a['verweise'])) {
                $s->abstand(3);
                $s->text('Geregelt in den QM-Dokumenten:', 8.5, false, '#5f5b55');
                foreach ($a['verweise'] as $v) {
                    $stand = ($v['dok'] ?? '') === '' ? '' : (($v['version'] ?? '') !== '' ? ' – Version ' . $v['version'] . (($v['datum'] ?? '') !== '' ? ' vom ' . qs_de((string)$v['datum']) : '') : ' – ohne gültige Version');
                    $s->text((string)$v['text'] . $stand, 9.5, false, '#1b1a18', 12, '•');
                }
            }
            $s->abstand(7);
        }
    }
    if (!empty($inhalt['systeme'])) {
        $s->platz(110);
        $s->abstand(10);
        $s->text('IT-Systeme', 13, true);
        $s->abstand(3);
        $s->linie();
        foreach ($inhalt['systeme'] as $x) {
            $s->platz(64);
            $s->abstand(4);
            $s->text((string)$x['name'] . ' · ' . (QS_VF_SYSTEM_ART[$x['art']] ?? (string)$x['art']) . (($x['bis'] ?? '') !== '' ? ' · außer Betrieb seit ' . qs_de((string)$x['bis']) : ''), 10.5, true);
            $s->paar('Zweck und Daten', (string)($x['zweck'] ?? ''));
            $s->paar('Anbieter / Version', (string)($x['anbieter'] ?? ''));
            $s->paar('Betrieb und Speicherort', (QS_VF_BETRIEB[$x['betrieb']] ?? (string)$x['betrieb']) . (($x['ort'] ?? '') !== '' ? ' – ' . $x['ort'] : ''));
            $s->paar('Zuständig', qs_vf_pdf_name($inhalt, (string)($x['zustaendig'] ?? '')));
            $s->paar('Sicherung, Aufbewahrung', (string)($x['sicherung'] ?? ''));
            $s->paar('Schnittstellen', (string)($x['schnittstellen'] ?? ''));
            $s->paar('Im Einsatz seit', ($x['seit'] ?? '') !== '' ? qs_de((string)$x['seit']) : '');
            $s->abstand(7);
        }
    }
    if (!empty($inhalt['dokumente'])) {
        $s->platz(80);
        $s->abstand(10);
        $s->text('Verknüpfte QM-Dokumente (Stand dieser Fassung)', 13, true);
        $s->abstand(3);
        $s->linie();
        foreach ($inhalt['dokumente'] as $d)
            $s->text(trim($d['nr'] . ' ' . $d['titel']) . ($d['version'] !== '' ? ' – Version ' . $d['version'] . ($d['datum'] !== '' ? ' vom ' . qs_de((string)$d['datum']) : '') : ' – ohne gültige Version'), 9.5, false, '#1b1a18', 12, '•');
    }
}
/* Ein Durchlauf. $k: art (fassung|entwurf|pruefung), von, bis, erstellt (Name), heute; $teile: Liste [f => Fassung mit Inhalt,
   bis => gültig bis]; $alle: alle Fassungen der Dokumentation (für die Übersicht). Liefert [PDF, Seitenzahl]. */
function qs_vf_pdf_lauf(array $doku, array $teile, array $alle, array $k, int $gesamt): array
{
    $entwurf = $k['art'] === 'entwurf';
    // Bezeichnung und Unternehmen aus dem Schnappschuss der (letzten enthaltenen) Fassung – nicht der heutige Stand (GR-106)
    $letzter = $teile[count($teile) - 1]['f']['inhalt'];
    $titel = (string)($letzter['titel'] ?? ''); $firma = (string)($letzter['gesellschaft'] ?? '');
    $s = new QsVfSatz(trim($titel . ($firma !== '' ? ' · ' . $firma : '')), $gesamt, $entwurf ? 'ENTWURF – nicht freigegeben' : '');
    // Deckblatt
    $s->abstand(70);
    $s->text('Verfahrensdokumentation', 24, true);
    $s->abstand(4);
    $s->text($titel, 13);
    if ($firma !== '') $s->text($firma, 13);
    $s->abstand(22);
    if ($k['art'] === 'pruefung') {
        $s->text('Export für die Prüfung', 11, true);
        $s->text('Prüfungszeitraum ' . qs_de($k['von']) . ' – ' . qs_de($k['bis']), 11);
    } elseif ($entwurf) {
        $s->text('Entwurf – nicht freigegeben', 11, true, '#b3261e');
        $s->text('Arbeitsstand vom ' . qs_de($k['heute']), 11);
    } else {
        $f = $teile[0]['f'];
        $s->text('Fassung ' . (int)$f['nr'], 11, true);
        $s->text(ucfirst(qs_vf_pdf_gueltig((string)$f['gueltigAb'], $teile[0]['bis'])), 11);
    }
    $s->abstand(14);
    $s->paar('Verantwortlich', qs_vf_pdf_name($letzter, (string)($letzter['verantwortlich'] ?? '')));
    $s->paar('Erstellt', 'am ' . qs_de($k['heute']) . ' von ' . $k['erstellt'] . ' aus dem QM-System');
    $s->paar('Grundlage', 'Grundsätze zur ordnungsmäßigen Führung und Aufbewahrung von Büchern, Aufzeichnungen und Unterlagen in elektronischer Form sowie zum Datenzugriff (GoBD), Rz. 151–155');
    $s->paar('Hinweis', 'Freigegebene Fassungen sind im QM-System unveränderlich gespeichert. Zu jedem verknüpften QM-Dokument ist die Version festgehalten, die am Tag der Freigabe galt.');
    // Übersicht der Fassungen = Änderungshistorie
    $s->abstand(22);
    $s->text('Fassungen und Änderungen', 13, true);
    $s->abstand(3);
    $s->linie();
    if (!$alle) $s->text('Noch keine freigegebene Fassung.', 9.5, false, '#5f5b55');
    $enthalten = array_map(function ($t) { return (int)($t['f']['nr'] ?? 0); }, $teile);
    foreach ($alle as $i => $f) {
        $s->platz(46);
        $s->text('Fassung ' . (int)$f['nr'] . ' · ' . qs_vf_pdf_gueltig((string)$f['gueltigAb'], qs_vf_gueltig_bis($alle, $i))
            . ($k['art'] === 'pruefung' && in_array((int)$f['nr'], $enthalten, true) ? ' · im Prüfungszeitraum' : ''), 10, true);
        $s->text('Freigegeben am ' . qs_de((string)$f['datum']) . ' von ' . (string)($f['freigegeben']['von'] ?? '') . ' · Anlass: ' . (string)$f['grund'], 9.5);
        foreach (is_array($f['aenderungen'] ?? null) ? $f['aenderungen'] : [] as $z) $s->text((string)$z, 9, false, '#3d3a36', 12, '•');
        $s->abstand(6);
    }
    $pruefungen = array_values(array_filter($doku['pruefungen'], function ($p) use ($k) { return $k['nur'] ? (int)($p['fassung'] ?? 0) === $k['nur'] : (string)($p['datum'] ?? '') <= $k['stand']; }));
    if ($pruefungen) {
        $s->platz(30);
        $s->text('Ohne Änderung überprüft', 10, true);
        foreach ($pruefungen as $p) $s->text(qs_de((string)($p['datum'] ?? '')) . ' von ' . (string)($p['von'] ?? '') . ((string)($p['notiz'] ?? '') !== '' ? ' – ' . $p['notiz'] : ''), 9, false, '#3d3a36', 12, '•');
    }
    // Inhalt je Fassung
    foreach ($teile as $t) {
        $f = $t['f'];
        $s->neueSeite();
        $s->text($entwurf ? 'Arbeitsstand vom ' . qs_de($k['heute']) : 'Fassung ' . (int)$f['nr'], 17, true);
        if (!$entwurf) $s->text(ucfirst(qs_vf_pdf_gueltig((string)$f['gueltigAb'], $t['bis'])) . ' · freigegeben am ' . qs_de((string)$f['datum']) . ' von ' . (string)($f['freigegeben']['von'] ?? ''), 9.5, false, '#5f5b55');
        qs_vf_pdf_inhalt($s, $f['inhalt']);
    }
    return [$s->pdf->output($titel), $s->seiten()];
}
function qs_vf_pdf(array $doku, array $teile, array $alle, array $k): string
{
    [, $seiten] = qs_vf_pdf_lauf($doku, $teile, $alle, $k, 0);
    return qs_vf_pdf_lauf($doku, $teile, $alle, $k, $seiten)[0];
}
/* Dateien der verknüpften QM-Dokumente in den Versionen, die die Fassungen festgehalten haben (für das ZIP) */
function qs_vf_export_dateien(array $teile, array $dokumente, string $wurzel): array
{
    $nachId = []; foreach ($dokumente as $d) $nachId[(string)$d['id']] = $d;
    $e = []; $gesehen = [];
    foreach ($teile as $t) foreach ($t['f']['inhalt']['dokumente'] ?? [] as $x) {
        $d = $nachId[(string)$x['dok']] ?? null;
        if ($d === null || (string)$x['version'] === '') continue;
        foreach ((array)($d['versionen'] ?? []) as $v) {
            if ((string)($v['nr'] ?? '') !== (string)$x['version'] || !in_array((string)($v['status'] ?? ''), ['freigegeben', 'ersetzt'], true)) continue;
            foreach (qs_dateien_aktiv($v['dateien'] ?? []) as $f) {
                if (isset($gesehen[(string)$f['id']])) continue;
                $gesehen[(string)$f['id']] = true;
                $e[] = ['pfad' => $wurzel . '/QM-Dokumente/' . ablage_zip_pfad(trim($x['nr'] . ' ' . $x['titel'])) . '/Version ' . ablage_zip_pfad((string)$x['version']) . '/' . ablage_zip_pfad((string)$f['name']),
                        'bereich' => 'qs', 'id' => (string)$f['id']];
            }
        }
    }
    return $e;
}
/* Export ausführen und senden (endet immer). $q: GET-Parameter fassung | von, bis, dokumente */
function qs_vf_export(array $doku, array $q, array $me, array $dokumente, array $stamm): void
{
    $heute = qs_heute();
    $alle = $doku['fassungen'];
    $k = ['heute' => $heute, 'erstellt' => (string)$me['name'], 'von' => '', 'bis' => '', 'stand' => $heute, 'nur' => 0];   // Überprüfungen bis zum Tag „stand“ bzw. nur die der Fassung „nur“
    $basis = 'Verfahrensdokumentation_' . ablage_zip_pfad($doku['gesellschaft'] !== '' ? $doku['gesellschaft'] : $doku['titel']);
    if (isset($q['fassung'])) {
        $nr = is_string($q['fassung']) && ctype_digit($q['fassung']) ? (int)$q['fassung'] : -1;
        if ($nr === 0) {
            $k['art'] = 'entwurf';
            $teile = [['f' => ['nr' => 0, 'inhalt' => qs_vf_inhalt($doku, $dokumente, $stamm)], 'bis' => '']];
            $name = $basis . '_Entwurf_' . $heute . '.pdf';
            $was = 'Entwurf';
        } else {
            $i = null;
            foreach ($alle as $j => $f) if ((int)($f['nr'] ?? 0) === $nr) $i = $j;
            if ($i === null) fail('Fassung nicht gefunden.', 404);
            $k['art'] = 'fassung';
            $teile = [['f' => $alle[$i], 'bis' => qs_vf_gueltig_bis($alle, $i)]];
            $k['nur'] = $nr;   // nur die Überprüfungen dieser Fassung
            $alle = array_slice($alle, 0, $i + 1);
            $name = $basis . '_Fassung-' . $nr . '.pdf';
            $was = 'Fassung ' . $nr;
        }
        audit('qs', 'QM-System: Verfahrensdokumentation „' . $doku['titel'] . '“ – ' . $was . ' als PDF geöffnet');
        qs_vf_pdf_senden(qs_vf_pdf($doku, $teile, $alle, $k), $name, true);
    }
    $von = qs_datum($q['von'] ?? '', 'Prüfungszeitraum von');
    $bis = qs_datum($q['bis'] ?? '', 'Prüfungszeitraum bis');
    if ($bis < $von) throw new InvalidArgumentException('Der Prüfungszeitraum endet vor seinem Beginn.');
    if (!$alle) throw new InvalidArgumentException('Es gibt noch keine freigegebene Fassung – ein Export für Prüfungen enthält nur freigegebene Fassungen.');
    $teile = [];
    foreach ($alle as $i => $f) {
        $ende = qs_vf_gueltig_bis($alle, $i);
        if ((string)$f['gueltigAb'] <= $bis && ($ende === '' || $ende >= $von)) $teile[] = ['f' => $f, 'bis' => $ende];
    }
    if (!$teile) throw new InvalidArgumentException('Im gewählten Zeitraum galt noch keine Fassung (die erste gilt ab ' . qs_de((string)$alle[0]['gueltigAb']) . ').');
    $k = ['art' => 'pruefung', 'von' => $von, 'bis' => $bis, 'stand' => min($bis, $heute)] + $k;
    $pdf = qs_vf_pdf($doku, $teile, $alle, $k);
    $name = $basis . '_Pruefung_' . $von . '_' . $bis;
    $nummern = implode(', ', array_map(function ($t) { return (int)$t['f']['nr']; }, $teile));
    if (($q['dokumente'] ?? '') !== '1') {
        audit('qs', 'QM-System: Verfahrensdokumentation „' . $doku['titel'] . '“ – Export für Prüfungen ' . qs_de($von) . ' – ' . qs_de($bis) . ' (Fassung ' . $nummern . ') als PDF heruntergeladen');
        qs_vf_pdf_senden($pdf, $name . '.pdf', false);
    }
    $dateien = qs_vf_export_dateien($teile, $dokumente, $name);
    audit('qs', 'QM-System: Verfahrensdokumentation „' . $doku['titel'] . '“ – Export für Prüfungen ' . qs_de($von) . ' – ' . qs_de($bis) . ' (Fassung ' . $nummern . ') als ZIP mit ' . count($dateien) . ' Dateien der QM-Dokumente heruntergeladen');
    ablage_zip_senden($name . '.zip', array_merge([['pfad' => $name . '/Verfahrensdokumentation.pdf', 'inhalt' => $pdf]], $dateien));
}
function qs_vf_pdf_senden(string $pdf, string $name, bool $inline): void
{
    header('Content-Type: application/pdf');
    header('Content-Disposition: ' . ($inline ? str_replace('attachment;', 'inline;', ablage_disposition($name)) : ablage_disposition($name)));
    header('Cache-Control: private, no-store');
    header('X-Content-Type-Options: nosniff');
    header('Content-Length: ' . strlen($pdf));
    echo $pdf;
    exit;
}
