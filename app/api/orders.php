<?php
/* Shared order operations for the website and future app clients. */
const ORDER_STATES = ['neu', 'in_bearbeitung', 'bestaetigt', 'erledigt', 'storniert'];
function order_view(array $o, bool $staff): array
{
    $out = array_intersect_key($o, array_flip(['nr','t','firma','angebot','angebotName','week','year','positions','total','totalQty','onRequest','termin','referenz','bemerkung']));
    $out['workflow'] = $o['workflow'] ?? 'neu';
    $out['revision'] = (int)($o['revision'] ?? 1);
    if ($staff) {
        $out['delivery'] = $o['status'] ?? 'neu';
        $out['deliveryError'] = $o['error'] ?? '';
        $out['assignee'] = $o['assignee'] ?? '';
        $out['note'] = $o['note'] ?? '';
        $out['history'] = $o['history'] ?? [];
        $out['kunde'] = $o['kunde'] ?? null;
    }
    return $out;
}
function order_receipt(array $o, bool $replayed = false): void
{
    respond(['ok' => true, 'apiVersion' => 1, 'nr' => $o['nr'], 'total' => $o['total'], 'totalQty' => $o['totalQty'],
        'positions' => count($o['positions']), 'onRequest' => $o['onRequest'], 'copy' => !empty($o['kopie']) ? ($o['kunde']['email'] ?? null) : null,
        'delivery' => $o['status'] ?? 'neu', 'replayed' => $replayed]);
}
function order_replay(array $all, string $kid, string $key, string $hash): void
{
    if ($key === '') return;
    foreach ($all as $o) if (($o['kid'] ?? '') === $kid && ($o['requestId'] ?? '') === $key) {
        if (!hash_equals((string)($o['requestHash'] ?? ''), $hash)) fail('Diese Übermittlungskennung wurde bereits für einen anderen Bestellwunsch verwendet.', 409);
        order_receipt($o, true); // Never send another email or create another order on a retry.
    }
}
function orders_action(string $action): bool
{
    $c = null;
    $customer = in_array($action, ['kunde_bestellungen', 'kunde_bestellung_detail'], true);
    if (!$customer && !in_array($action, ['bestellungen', 'bestellung', 'bestellung_save'], true)) return false;
    header('Cache-Control: private, no-store');
    if ($customer) {
        $c = current_customer();
        if (!$c) fail('Bitte anmelden.', 401);
        if (!empty($c['login']['mustChange'])) fail('Bitte zuerst ein eigenes Passwort festlegen.', 403);
    } else $me = require_auth($action === 'bestellung_save', 'editor');
    if ($action === 'bestellung_save') {
        $b = body();
        foreach (['nr','workflow','assignee','note'] as $field) if (!is_string($b[$field] ?? null)) fail('Ungültiges Feld: ' . $field, 422);
        $result = with_lock('bestellungen', function () use ($b, $me) {
            $all = store_read('bestellungen') ?? [];
            foreach ($all as $i => $o) if ($o['nr'] === (string)($b['nr'] ?? '')) {
                if (!is_int($b['revision'] ?? null) || $b['revision'] !== (int)($o['revision'] ?? 1)) fail('Der Bestellwunsch wurde inzwischen geändert. Bitte neu laden.', 409);
                $state = (string)($b['workflow'] ?? '');
                $from = $o['workflow'] ?? 'neu';
                $allowed = ['neu'=>['in_bearbeitung','storniert'], 'in_bearbeitung'=>['neu','bestaetigt','storniert'], 'bestaetigt'=>['in_bearbeitung','erledigt','storniert'], 'erledigt'=>[], 'storniert'=>[]];
                if (!in_array($state, ORDER_STATES, true) || ($state !== $from && !in_array($state, $allowed[$from] ?? [], true))) fail('Dieser Statuswechsel ist nicht möglich.', 422);
                $assignee = (string)($b['assignee'] ?? '');
                if ($assignee !== '') {
                    $valid = false;
                    foreach (users_load() as $u) if ($u['id'] === $assignee && !empty($u['active']) && in_array($u['role'], ['editor','admin'], true)) $valid = true;
                    if (!$valid) fail('Bitte einen aktiven Bearbeiter wählen.', 422);
                }
                $note = trim((string)($b['note'] ?? ''));
                if (mb_strlen($note) > 2000) fail('Interne Notiz ist zu lang (höchstens 2.000 Zeichen).', 422);
                $o['workflow'] = $state; $o['assignee'] = $assignee; $o['note'] = $note;
                $o['revision'] = (int)($o['revision'] ?? 1) + 1;
                $o['history'][] = ['t'=>now(), 'by'=>$me['name'], 'from'=>$from, 'to'=>$state, 'assignee'=>$assignee, 'note'=>$note];
                $all[$i] = $o; store_write('bestellungen', $all);
                return order_view($o, true);
            }
            fail('Bestellwunsch nicht gefunden.', 404);
        });
        audit('bestellung', 'Bestellwunsch ' . $result['nr'] . ': ' . $result['workflow']);
        respond(['ok'=>true, 'apiVersion'=>1, 'order'=>$result]);
    }
    $all = array_values(array_filter(store_read('bestellungen') ?? [], fn($o) => !$customer || ($o['kid'] ?? '') === $c['id']));
    if (in_array($action, ['bestellung','kunde_bestellung_detail'], true)) {
        foreach ($all as $o) if ($o['nr'] === (string)($_GET['nr'] ?? '')) respond(['ok'=>true,'apiVersion'=>1,'order'=>order_view($o, !$customer)]);
        fail('Bestellwunsch nicht gefunden.', 404);
    }
    $q = mb_strtolower(mb_substr(trim((string)($_GET['q'] ?? '')), 0, 100));
    $state = (string)($_GET['workflow'] ?? '');
    if ($state !== '' && !in_array($state, ORDER_STATES, true)) fail('Ungültiger Status.', 422);
    $all = array_values(array_filter(array_reverse($all), fn($o) => ($state === '' || ($o['workflow'] ?? 'neu') === $state) && ($q === '' || mb_strpos(mb_strtolower($o['nr'] . ' ' . $o['firma'] . ' ' . ($o['referenz'] ?? '')), $q) !== false)));
    $offset = max(0, min(1000000, (int)($_GET['offset'] ?? 0))); $limit = max(1, min(100, (int)($_GET['limit'] ?? 25)));
    $rows = array_map(fn($o) => order_view($o, !$customer), array_slice($all, $offset, $limit));
    // List responses omit position arrays; detail endpoint delivers the immutable snapshot.
    foreach ($rows as &$row) { $row['positionCount'] = count($row['positions'] ?? []); unset($row['positions'], $row['history'], $row['note'], $row['kunde']); } unset($row);
    $out = ['ok'=>true,'apiVersion'=>1,'orders'=>$rows,'total'=>count($all),'offset'=>$offset,'limit'=>$limit];
    if (!$customer) $out['assignees'] = array_values(array_map(fn($u) => ['id'=>$u['id'],'name'=>$u['name']], array_filter(users_load(), fn($u) => !empty($u['active']) && in_array($u['role'], ['editor','admin'], true))));
    respond($out);
}
