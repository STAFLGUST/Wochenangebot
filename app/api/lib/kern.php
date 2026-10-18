<?php
declare(strict_types=1);
/* Antworten, Eingaben, Datenprüfung */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Hilfsfunktionen ---------------- */

/* Testumgebung (test.<Domain>): nur Testdaten; E-Mails gehen in das Testpostfach statt an echte Empfänger */
function testumgebung(): bool { return getenv('WA_TESTUMGEBUNG') === '1'; }
function respond(array $data, int $status = 200): void
{
    store_commit(); // Intentional API errors may persist login-attempt counters.
    http_response_code($status);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}
function fail(string $msg, int $status = 400): void { respond(['ok' => false, 'error' => $msg], $status); }

function body(): array
{
    $raw = file_get_contents('php://input', false, null, 0, 6 * 1024 * 1024 + 1);
    if ($raw === false || strlen($raw) > 6 * 1024 * 1024) fail('Anfrage ist zu groß.', 413);
    $data = json_decode($raw ?: '{}', true);
    if (!is_array($data)) fail('Ungültige Anfrage.');
    return $data;
}
function now(): string { return gmdate('Y-m-d\TH:i:s\Z'); }

/* ---------------- Datenprüfung ---------------- */

function s($v, int $max, bool $allowEmpty = true): ?string
{
    if ($v === null) return null;
    if (!is_string($v) && !is_int($v) && !is_float($v)) return null;
    $v = trim(preg_replace('/\s+/u', ' ', (string)$v) ?? '');
    if (!$allowEmpty && $v === '') return null;
    return mb_substr($v, 0, $max);
}
function clean_price($p, string $where): array
{
    if (!is_array($p)) throw new InvalidArgumentException("Preisangabe fehlt ($where).");
    $st = $p['status'] ?? '';
    if (!in_array($st, PRICE_STATUS, true)) throw new InvalidArgumentException("Ungültiger Preisstatus ($where).");
    $out = ['status' => $st];
    if ($st === 'value') {
        $v = $p['value'] ?? null;
        if (!is_int($v) && !is_float($v)) throw new InvalidArgumentException("Preis fehlt ($where).");
        $v = (float)$v;
        if ($v < 0 || $v >= 100000) throw new InvalidArgumentException("Preis außerhalb des gültigen Bereichs ($where).");
        $out['value'] = round($v, 4);
    }
    $raw = s($p['raw'] ?? null, 60);
    if ($raw !== null && $raw !== '') $out['raw'] = $raw;
    $label = s($p['label'] ?? null, 40);
    if ($label !== null && $label !== '') $out['label'] = $label;
    return $out;
}
