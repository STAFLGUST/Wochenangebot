<?php
declare(strict_types=1);
/* Schlanker PDF-Erzeuger (ohne Fremdbibliothek): Seiten, Standardschriften Helvetica/Helvetica-Bold (WinAnsi, also auch
   ä ö ü ß €), Text, Linien, Flächen und ein JPEG-Bild. Koordinaten in Punkt (1/72 Zoll), Ursprung oben links.
   Nur bei Bedarf geladen (require_once aus lib/einzelangebote.php). */
if (!defined('WA_API')) { http_response_code(404); exit; }
require_once __DIR__ . '/pdf-breiten.php';

final class Pdf
{
    private array $pages = [];
    private string $cur = '';
    private array $images = [];
    public function __construct(public float $w = 841.89, public float $h = 595.28) {}

    public function addPage(): void { if ($this->cur !== '' || $this->pages) $this->pages[] = $this->cur; $this->cur = ''; }
    public function pageCount(): int { return count($this->pages) + 1; }

    /* UTF-8 → Windows-1252 (nicht darstellbare Zeichen werden „?“) */
    public static function enc(string $s): string
    {
        $s = preg_replace('/[\x00-\x1f]/u', ' ', $s) ?? '';
        $r = @iconv('UTF-8', 'Windows-1252//TRANSLIT', $s);
        if ($r === false) $r = mb_convert_encoding($s, 'Windows-1252', 'UTF-8');
        return $r;
    }
    public static function width(string $s, float $size, bool $bold = false): float
    {
        $t = self::enc($s);
        $w = 0;
        $tab = $bold ? PDF_W_HELVB : PDF_W_HELV;
        for ($i = 0, $n = strlen($t); $i < $n; $i++) $w += $tab[ord($t[$i])];
        return $w * $size / 1000;
    }
    /* Zeilenumbruch nach Wörtern; zu lange Wörter werden hart getrennt */
    public static function wrap(string $s, float $size, float $max, bool $bold = false): array
    {
        $out = []; $line = '';
        foreach (preg_split('/\s+/u', trim($s)) ?: [] as $word) {
            if ($word === '') continue;
            $try = $line === '' ? $word : $line . ' ' . $word;
            if (self::width($try, $size, $bold) <= $max) { $line = $try; continue; }
            if ($line !== '') $out[] = $line;
            while (self::width($word, $size, $bold) > $max && mb_strlen($word) > 1) {
                $k = mb_strlen($word);
                while ($k > 1 && self::width(mb_substr($word, 0, $k), $size, $bold) > $max) $k--;
                $out[] = mb_substr($word, 0, $k); $word = mb_substr($word, $k);
            }
            $line = $word;
        }
        if ($line !== '') $out[] = $line;
        return $out ?: [''];
    }
    private static function esc(string $t): string { return strtr($t, ['\\' => '\\\\', '(' => '\(', ')' => '\)', "\r" => ' ', "\n" => ' ']); }
    private static function col(string $hex): string
    {
        $hex = ltrim($hex, '#');
        return implode(' ', array_map(fn($i) => sprintf('%.3F', hexdec(substr($hex, $i, 2)) / 255), [0, 2, 4]));
    }
    private function y(float $y): float { return $this->h - $y; }

    /* Text an Grundlinie y; align: l, r (x = rechter Rand) */
    public function text(float $x, float $y, string $s, float $size = 9, bool $bold = false, string $color = '#111111', string $align = 'l'): void
    {
        if ($align === 'r') $x -= self::width($s, $size, $bold);
        $this->cur .= sprintf("BT /%s %.2F Tf %s rg %.2F %.2F Td (%s) Tj ET\n", $bold ? 'F2' : 'F1', $size, self::col($color), $x, $this->y($y), self::esc(self::enc($s)));
    }
    public function rect(float $x, float $y, float $w, float $h, string $fill): void
    {
        $this->cur .= sprintf("%s rg %.2F %.2F %.2F %.2F re f\n", self::col($fill), $x, $this->y($y + $h), $w, $h);
    }
    public function line(float $x1, float $y1, float $x2, float $y2, float $lw = .5, string $color = '#111111'): void
    {
        $this->cur .= sprintf("%s RG %.2F w %.2F %.2F m %.2F %.2F l S\n", self::col($color), $lw, $x1, $this->y($y1), $x2, $this->y($y2));
    }
    /* JPEG einbinden (Breite in pt; Höhe aus dem Seitenverhältnis); liefert die Höhe */
    public function jpeg(string $file, float $x, float $y, float $w): float
    {
        $info = @getimagesize($file);
        if (!$info || ($info[2] ?? 0) !== IMAGETYPE_JPEG) return 0;
        $key = 'I' . (count($this->images) + 1);
        foreach ($this->images as $k => $im) if ($im['file'] === $file) $key = $k;
        $this->images[$key] = ['file' => $file, 'w' => $info[0], 'h' => $info[1], 'ch' => ($info['channels'] ?? 3) === 1 ? 'DeviceGray' : 'DeviceRGB'];
        $h = $w * $info[1] / $info[0];
        $this->cur .= sprintf("q %.2F 0 0 %.2F %.2F %.2F cm /%s Do Q\n", $w, $h, $x, $this->y($y + $h), $key);
        return $h;
    }

    public function output(string $title = ''): string
    {
        $pages = $this->pages; $pages[] = $this->cur;
        $obj = [];   // Nummer => Inhalt
        $n = 2;      // 1 Katalog, 2 Seitenbaum
        $font1 = ++$n; $obj[$font1] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>';
        $font2 = ++$n; $obj[$font2] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>';
        $xo = [];
        foreach ($this->images as $k => $im) {
            $data = (string)file_get_contents($im['file']);
            $id = ++$n; $xo[] = "/$k $id 0 R";
            $obj[$id] = sprintf("<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /%s /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n%s\nendstream",
                $im['w'], $im['h'], $im['ch'], strlen($data), $data);
        }
        $res = "<< /Font << /F1 $font1 0 R /F2 $font2 0 R >>" . ($xo ? ' /XObject << ' . implode(' ', $xo) . ' >>' : '') . ' >>';
        $kids = [];
        foreach ($pages as $p) {
            $c = gzcompress($p);
            $cid = ++$n; $obj[$cid] = sprintf("<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream", strlen($c), $c);
            $pid = ++$n; $obj[$pid] = sprintf('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2F %.2F] /Resources %s /Contents %d 0 R >>', $this->w, $this->h, $res, $cid);
            $kids[] = "$pid 0 R";
        }
        $obj[1] = '<< /Type /Catalog /Pages 2 0 R >>';
        $obj[2] = '<< /Type /Pages /Kids [' . implode(' ', $kids) . '] /Count ' . count($kids) . ' >>';
        $info = ++$n;
        $obj[$info] = '<< /Title (' . self::esc(self::enc($title)) . ') /Producer (Wochenangebot) /CreationDate (D:' . gmdate('YmdHis') . 'Z) >>';
        ksort($obj);
        $out = "%PDF-1.4\n%\xE2\xE3\xCF\xD3\n";
        $off = [];
        foreach ($obj as $i => $body) { $off[$i] = strlen($out); $out .= "$i 0 obj\n$body\nendobj\n"; }
        $xref = strlen($out);
        $out .= 'xref' . "\n0 " . ($n + 1) . "\n0000000000 65535 f \n";
        for ($i = 1; $i <= $n; $i++) $out .= sprintf("%010d 00000 n \n", $off[$i]);
        $out .= "trailer\n<< /Size " . ($n + 1) . " /Root 1 0 R /Info $info 0 R >>\nstartxref\n$xref\n%%EOF\n";
        return $out;
    }
}
