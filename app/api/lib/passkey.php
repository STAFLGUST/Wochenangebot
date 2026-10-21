<?php
declare(strict_types=1);
/* Passkeys (WebAuthn) für Mitarbeiter-Zugänge – ohne Fremdbibliothek.
   Registrierung mit Attestierung „none“ (Attestierungen anderer Formate werden nicht geprüft, nur angenommen),
   Anmeldung mit auffindbaren Schlüsseln (ohne Benutzername) oder als zweiter Schritt nach dem Passwort.
   Gespeichert je Nutzer im Feld `passkeys` (optional; ältere Daten ohne das Feld bleiben gültig):
   [{id (Credential-ID, base64url), publicKey (PEM), alg (-7|-257), signCount, name, created, lastUsed, transports}] */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const PASSKEY_MAX = 10;
const PASSKEY_TTL = 300;           // Gültigkeit einer Anfrage (Sekunden)
const PASSKEY_ALGS = [-7, -257];   // ES256, RS256
const PASSKEY_TRANSPORTS = ['usb', 'nfc', 'ble', 'internal', 'hybrid', 'smart-card'];

function b64u_enc(string $bin): string { return rtrim(strtr(base64_encode($bin), '+/', '-_'), '='); }
function b64u_dec($s): ?string
{
    if (!is_string($s) || $s === '' || strlen($s) > 65536 || !preg_match('/^[A-Za-z0-9_-]+=*$/D', $s)) return null;
    $bin = base64_decode(strtr(rtrim($s, '='), '-_', '+/'), true);
    return $bin === false ? null : $bin;
}

function has_passkeys(array $u): bool { return !empty($u['passkeys']) && is_array($u['passkeys']); }
/* Zweiter Faktor vorhanden: Authenticator-App oder mindestens ein Passkey */
function has_second_factor(array $u): bool { return !empty($u['totp']) || has_passkeys($u); }
/* Kurzer Verweis für die Oberfläche (statt der Credential-ID) */
function passkey_ref(array $pk): string { return substr(hash('sha256', (string)$pk['id']), 0, 16); }
function passkey_public(array $u): array
{
    $out = [];
    foreach ((array)($u['passkeys'] ?? []) as $pk) $out[] = ['ref' => passkey_ref($pk), 'name' => (string)($pk['name'] ?? ''), 'created' => $pk['created'] ?? null, 'lastUsed' => $pk['lastUsed'] ?? null];
    return $out;
}

/* Relying Party = aufgerufener Host ohne Port (keine IP-Adressen – WebAuthn erlaubt sie nicht) */
function passkey_host(): string
{
    $h = strtolower(trim((string)($_SERVER['HTTP_HOST'] ?? '')));
    if (!preg_match('/^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?(:\d{1,5})?$/D', $h)) fail('Passkeys sind unter dieser Adresse nicht möglich.', 400);
    return $h;
}
function passkey_rp_id(): string
{
    $id = explode(':', passkey_host(), 2)[0];
    if (filter_var($id, FILTER_VALIDATE_IP)) fail('Passkeys funktionieren nicht mit einer IP-Adresse – bitte die Seite über ihren Namen aufrufen.', 400);
    return $id;
}
function passkey_origin(): string { return (is_https() ? 'https' : 'http') . '://' . passkey_host(); }

/* ---------- Minimaler CBOR-Leser (RFC 8949): Zahlen, Byte-/Textfolgen, Listen, Maps, einfache Werte ---------- */
function cbor_decode(string $data, int &$pos = 0, int $depth = 0)
{
    if ($depth > 16) throw new InvalidArgumentException('CBOR zu tief verschachtelt.');
    $len = strlen($data);
    if ($pos >= $len) throw new InvalidArgumentException('CBOR unvollständig.');
    $ib = ord($data[$pos++]);
    $major = $ib >> 5;
    $info = $ib & 0x1f;
    if ($major === 7) {
        if ($info === 20) return false;
        if ($info === 21) return true;
        if ($info === 22 || $info === 23) return null;
        if ($info < 20) return $info;   // unbenannter einfacher Wert
        if ($info === 24) { cbor_need($data, $pos, 1); return ord($data[$pos++]); }
        if ($info === 25) { cbor_need($data, $pos, 2); $h = unpack('n', substr($data, $pos, 2))[1]; $pos += 2; return cbor_half($h); }
        if ($info === 26) { cbor_need($data, $pos, 4); $f = unpack('G', substr($data, $pos, 4))[1]; $pos += 4; return $f; }
        if ($info === 27) { cbor_need($data, $pos, 8); $f = unpack('E', substr($data, $pos, 8))[1]; $pos += 8; return $f; }
        throw new InvalidArgumentException('CBOR: nicht unterstützter Wert.');
    }
    if ($info < 24) $val = $info;
    elseif ($info === 24) { cbor_need($data, $pos, 1); $val = ord($data[$pos]); $pos += 1; }
    elseif ($info === 25) { cbor_need($data, $pos, 2); $val = unpack('n', substr($data, $pos, 2))[1]; $pos += 2; }
    elseif ($info === 26) { cbor_need($data, $pos, 4); $val = unpack('N', substr($data, $pos, 4))[1]; $pos += 4; }
    elseif ($info === 27) {
        cbor_need($data, $pos, 8);
        $hi = unpack('N', substr($data, $pos, 4))[1]; $lo = unpack('N', substr($data, $pos + 4, 4))[1]; $pos += 8;
        if ($hi > 0x7fffffff) throw new InvalidArgumentException('CBOR: Zahl zu groß.');
        $val = ($hi << 32) | $lo;
    } else throw new InvalidArgumentException('CBOR: unbestimmte Längen werden nicht unterstützt.');
    switch ($major) {
        case 0: return $val;
        case 1: return -1 - $val;
        case 2:
        case 3:
            cbor_need($data, $pos, $val);
            $s = substr($data, $pos, $val); $pos += $val;
            return $s;
        case 4:
            if ($val > $len - $pos) throw new InvalidArgumentException('CBOR: Liste zu lang.');
            $a = [];
            for ($i = 0; $i < $val; $i++) $a[] = cbor_decode($data, $pos, $depth + 1);
            return $a;
        case 5:
            if ($val * 2 > $len - $pos) throw new InvalidArgumentException('CBOR: Map zu lang.');
            $m = [];
            for ($i = 0; $i < $val; $i++) {
                $k = cbor_decode($data, $pos, $depth + 1);
                if (!is_int($k) && !is_string($k)) throw new InvalidArgumentException('CBOR: ungültiger Schlüssel.');
                $m[$k] = cbor_decode($data, $pos, $depth + 1);
            }
            return $m;
        case 6: return cbor_decode($data, $pos, $depth + 1);   // Tag: nur der Inhalt zählt
    }
    throw new InvalidArgumentException('CBOR ungültig.');
}
function cbor_need(string $data, int $pos, int $n): void { if ($n < 0 || $pos + $n > strlen($data)) throw new InvalidArgumentException('CBOR unvollständig.'); }
function cbor_half(int $h): float
{
    $exp = ($h >> 10) & 0x1f; $mant = $h & 0x3ff;
    $v = $exp === 0 ? $mant * 2 ** -24 : ($exp !== 31 ? ($mant + 1024) * 2 ** ($exp - 25) : ($mant === 0 ? INF : NAN));
    return ($h & 0x8000) ? -$v : $v;
}

/* ---------- Schlüssel: COSE → PEM ---------- */
function der_len(int $n): string
{
    if ($n < 0x80) return chr($n);
    $b = ''; while ($n > 0) { $b = chr($n & 0xff) . $b; $n >>= 8; }
    return chr(0x80 | strlen($b)) . $b;
}
function der(int $tag, string $body): string { return chr($tag) . der_len(strlen($body)) . $body; }
function der_uint(string $bin): string
{
    $bin = ltrim($bin, "\0");
    if ($bin === '' || ord($bin[0]) & 0x80) $bin = "\0" . $bin;
    return der(0x02, $bin);
}
function pem_public(string $spki): string { return "-----BEGIN PUBLIC KEY-----\n" . chunk_split(base64_encode($spki), 64, "\n") . "-----END PUBLIC KEY-----\n"; }
/* Liefert [alg, PEM]; nur ES256 (P-256) und RS256 */
function cose_to_pem(array $k): array
{
    $alg = $k[3] ?? null;
    if ($alg === -7) {
        if (($k[1] ?? null) !== 2 || ($k[-1] ?? null) !== 1 || !is_string($k[-2] ?? null) || !is_string($k[-3] ?? null) || strlen($k[-2]) !== 32 || strlen($k[-3]) !== 32) throw new InvalidArgumentException('Ungültiger EC-Schlüssel.');
        $algId = der(0x30, der(0x06, "\x2a\x86\x48\xce\x3d\x02\x01") . der(0x06, "\x2a\x86\x48\xce\x3d\x03\x01\x07"));   // ecPublicKey, prime256v1
        $spki = der(0x30, $algId . der(0x03, "\0\x04" . $k[-2] . $k[-3]));
    } elseif ($alg === -257) {
        if (($k[1] ?? null) !== 3 || !is_string($k[-1] ?? null) || !is_string($k[-2] ?? null) || strlen(ltrim($k[-1], "\0")) < 256 || strlen($k[-2]) > 8) throw new InvalidArgumentException('Ungültiger RSA-Schlüssel.');
        $algId = der(0x30, der(0x06, "\x2a\x86\x48\x86\xf7\x0d\x01\x01\x01") . "\x05\x00");   // rsaEncryption, NULL
        $spki = der(0x30, $algId . der(0x03, "\0" . der(0x30, der_uint($k[-1]) . der_uint($k[-2]))));
    } else throw new InvalidArgumentException('Dieses Schlüsselverfahren wird nicht unterstützt.');
    $pem = pem_public($spki);
    $key = openssl_pkey_get_public($pem);
    if ($key === false) throw new InvalidArgumentException('Der öffentliche Schlüssel ist ungültig.');
    return [$alg, $pem];
}

/* ---------- Authenticator-Daten ---------- */
/* Prüft rpIdHash und die Flags UP + UV; mit $attested zusätzlich AT und liest Credential-ID und Schlüssel */
function passkey_auth_data(string $ad, bool $attested): array
{
    if (strlen($ad) < 37) throw new InvalidArgumentException('Authenticator-Daten unvollständig.');
    if (!hash_equals(hash('sha256', passkey_rp_id(), true), substr($ad, 0, 32))) throw new InvalidArgumentException('Der Passkey gehört zu einer anderen Adresse.');
    $flags = ord($ad[32]);
    if (!($flags & 0x01)) throw new InvalidArgumentException('Anwesenheit nicht bestätigt.');
    if (!($flags & 0x04)) throw new InvalidArgumentException('Das Gerät hat die Person nicht geprüft (PIN, Fingerabdruck oder Gesicht nötig).');
    $out = ['flags' => $flags, 'signCount' => unpack('N', substr($ad, 33, 4))[1]];
    if (!$attested) return $out;
    if (!($flags & 0x40) || strlen($ad) < 55) throw new InvalidArgumentException('Im Passkey fehlen die Schlüsseldaten.');
    $out['aaguid'] = bin2hex(substr($ad, 37, 16));
    $n = unpack('n', substr($ad, 53, 2))[1];
    if ($n < 16 || $n > 1023 || strlen($ad) < 55 + $n) throw new InvalidArgumentException('Ungültige Passkey-Kennung.');
    $out['credId'] = substr($ad, 55, $n);
    $pos = 55 + $n;
    $cose = cbor_decode($ad, $pos);
    if (!is_array($cose)) throw new InvalidArgumentException('Ungültiger Schlüssel.');
    $out['cose'] = $cose;
    return $out;
}
/* clientDataJSON: Art, Anfrage (Challenge) und Herkunft prüfen */
function passkey_client_data(string $raw, string $type, string $challenge): array
{
    $c = json_decode($raw, true);
    if (!is_array($c) || ($c['type'] ?? '') !== $type) throw new InvalidArgumentException('Ungültige Passkey-Antwort.');
    if (!is_string($c['challenge'] ?? null) || !hash_equals($challenge, $c['challenge'])) throw new InvalidArgumentException('Die Anfrage passt nicht (abgelaufen oder bereits verwendet).');
    if (!is_string($c['origin'] ?? null) || !hash_equals(passkey_origin(), strtolower($c['origin']))) throw new InvalidArgumentException('Der Passkey wurde auf einer anderen Seite verwendet.');
    if (!empty($c['crossOrigin'])) throw new InvalidArgumentException('Der Passkey wurde in einem fremden Rahmen verwendet.');
    return $c;
}

/* Neue Anfrage (Challenge) in der Sitzung ablegen: $kind = 'pkReg' | 'pkAuth' */
function passkey_challenge(string $kind, array $extra = []): string
{
    $c = b64u_enc(random_bytes(32));
    $_SESSION[$kind] = ['c' => $c, 't' => time()] + $extra;
    return $c;
}
/* Anfrage einmalig entnehmen (gilt 5 Minuten) */
function passkey_take(string $kind): ?array
{
    $p = $_SESSION[$kind] ?? null;
    unset($_SESSION[$kind]);
    if (!is_array($p) || !is_string($p['c'] ?? null) || (int)($p['t'] ?? 0) < time() - PASSKEY_TTL) return null;
    return $p;
}

/* Optionen für navigator.credentials.create() */
function passkey_create_options(array $u, string $challenge): array
{
    global $CFG;
    $ex = [];
    foreach ((array)($u['passkeys'] ?? []) as $pk) $ex[] = ['type' => 'public-key', 'id' => $pk['id']];
    return ['challenge' => $challenge, 'rp' => ['id' => passkey_rp_id(), 'name' => ($CFG['company'] ?: 'Wochenangebot') . ' Wochenangebot'],
            'user' => ['id' => b64u_enc((string)$u['id']), 'name' => $u['username'], 'displayName' => $u['name']],
            'pubKeyCredParams' => array_map(fn($a) => ['type' => 'public-key', 'alg' => $a], PASSKEY_ALGS),
            'timeout' => PASSKEY_TTL * 1000, 'attestation' => 'none', 'excludeCredentials' => $ex,
            'authenticatorSelection' => ['residentKey' => 'required', 'requireResidentKey' => true, 'userVerification' => 'required']];
}

/* Registrierung prüfen; liefert den zu speichernden Eintrag (ohne Name) */
function passkey_verify_registration(array $b, string $challenge): array
{
    $cdRaw = b64u_dec($b['clientDataJSON'] ?? null);
    $att = b64u_dec($b['attestationObject'] ?? null);
    if ($cdRaw === null || $att === null) throw new InvalidArgumentException('Ungültige Passkey-Antwort.');
    passkey_client_data($cdRaw, 'webauthn.create', $challenge);
    $pos = 0;
    $obj = cbor_decode($att, $pos);
    if (!is_array($obj) || !is_string($obj['fmt'] ?? null) || !is_string($obj['authData'] ?? null)) throw new InvalidArgumentException('Ungültige Passkey-Antwort.');
    // Attestierung wird nicht ausgewertet (angefordert ist „none“); andere Formate werden ohne Prüfung angenommen.
    $ad = passkey_auth_data($obj['authData'], true);
    $id = b64u_enc($ad['credId']);
    if (isset($b['id']) && $b['id'] !== $id) throw new InvalidArgumentException('Ungültige Passkey-Antwort.');
    [$alg, $pem] = cose_to_pem($ad['cose']);
    $tr = array_values(array_intersect(PASSKEY_TRANSPORTS, array_filter((array)($b['transports'] ?? []), 'is_string')));
    $e = ['id' => $id, 'publicKey' => $pem, 'alg' => $alg, 'signCount' => (int)$ad['signCount'], 'created' => now(), 'lastUsed' => null];
    if ($tr) $e['transports'] = $tr;
    return $e;
}

/* Signatur einer Anmeldung prüfen (Daten bereits auf Herkunft/Challenge geprüft) */
function passkey_signature_ok(array $pk, string $authData, string $clientDataRaw, string $sig): bool
{
    if (!in_array((int)($pk['alg'] ?? 0), PASSKEY_ALGS, true) || $sig === '') return false;
    $key = openssl_pkey_get_public((string)($pk['publicKey'] ?? ''));
    if ($key === false) return false;
    // ES256: Signatur liegt bei WebAuthn bereits DER-codiert vor – passt direkt zu openssl_verify
    return openssl_verify($authData . hash('sha256', $clientDataRaw, true), $sig, $key, OPENSSL_ALGO_SHA256) === 1;
}

/* Optionen für navigator.credentials.get(); ohne Nutzer: auffindbare Schlüssel (leere allowCredentials) */
function passkey_get_options(string $challenge, ?array $u = null): array
{
    $allow = [];
    if ($u) foreach ((array)($u['passkeys'] ?? []) as $pk) $allow[] = ['type' => 'public-key', 'id' => $pk['id']] + (!empty($pk['transports']) ? ['transports' => $pk['transports']] : []);
    return ['challenge' => $challenge, 'rpId' => passkey_rp_id(), 'timeout' => PASSKEY_TTL * 1000, 'userVerification' => 'required', 'allowCredentials' => $allow];
}

/* Name eines Passkeys (Vorgabe „Passkey N“) */
function passkey_name($v, array $u): string
{
    $n = s($v, 60) ?? '';
    $n = preg_replace('/[\x00-\x1f\x7f]/u', '', $n) ?? '';
    if ($n !== '') return $n;
    $used = array_map(fn($p) => (string)($p['name'] ?? ''), (array)($u['passkeys'] ?? []));
    for ($i = count($used) + 1; ; $i++) if (!in_array("Passkey $i", $used, true)) return "Passkey $i";
}
