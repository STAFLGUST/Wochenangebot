<?php
/* Isolated calendar/history selection tests, no server or production storage. */
declare(strict_types=1);
const WA_API = true;
$docs = [];
function store_read(string $name) { return $GLOBALS['docs'][$name] ?? null; }
function store_names(string $prefix): array { return array_values(array_filter(array_keys($GLOBALS['docs']), fn($n) => str_starts_with($n, $prefix . '/'))); }
function now(): string { return '2026-10-19T12:00:00Z'; }
require __DIR__ . '/../../app/api/lib/preisverlauf.php';
require __DIR__ . '/../../app/api/lib/bestand.php';
$count = 0;
function check(string $name, bool $ok): void {
    $GLOBALS['count']++;
    if (!$ok) { fwrite(STDERR, "FAIL $name\n"); exit(1); }
    echo "PASS $name\n";
}
$r = stock_week_prices(new DateTimeImmutable('2027-01-04T12:00:00+01:00'));
check('ISO year boundary', $r['current']['week'] === 1 && $r['current']['year'] === 2027 && $r['previous']['week'] === 53 && $r['previous']['year'] === 2026);
$r = stock_week_prices(new DateTimeImmutable('2026-10-18T22:30:00Z'));
check('Berlin Monday despite UTC Sunday', $r['current']['week'] === 43 && $r['previous']['week'] === 42);
$docs['historie/2026-41'] = ['items' => [['code'=>'1','price'=>['status'=>'value','value'=>10]]]];
$r = stock_week_prices(new DateTimeImmutable('2026-10-19'));
check('history gap never replaced by older week', !$r['previous']['available'] && $r['previous']['items'] === []);
$docs['angebot'] = ['meta'=>['week'=>43,'year'=>2026], 'publishedAt'=>'2026-10-19T10:00:00Z', 'items'=>[['code'=>'1','price'=>['status'=>'value','value'=>12],'variants'=>['secret'=>['value'=>99]]]]];
$r = stock_week_prices(new DateTimeImmutable('2026-10-19'));
check('published exact week fallback', $r['current']['items'][0]['price']['value'] === 12);
check('no customer variants returned', array_keys($r['current']['items'][0]) === ['code','price']);
$docs['historie/2026-43'] = ['items'=>[['code'=>'1','price'=>['status'=>'value','value'=>13]]]];
$r = stock_week_prices(new DateTimeImmutable('2026-10-19'));
check('explicit historical week wins', $r['current']['items'][0]['price']['value'] === 13);
unset($docs['historie/2026-43']); $docs['historie_geloescht'] = ['2026-43'];
$r = stock_week_prices(new DateTimeImmutable('2026-10-19'));
check('deleted week not resurrected', !$r['current']['available']);
echo "$count/$count passed\n";
