<?php
/*
 * Dienst „postausgang“ (ADR-007, Postausgang von innen): ein Durchgang – fällige Versandaufträge der Kundenseite verschicken
 * (lib/postausgang.php) und ein Lebenszeichen schreiben. Läuft nur auf der Kommandozeile, nie über den Webserver.
 *
 *   php api/postausgang.php            ein Durchgang (der Dienst ruft das alle paar Sekunden in einer Schleife auf,
 *                                      deploy/anmeldung/docker-compose.anmeldung.yml – jeder Durchgang ist ein neuer Prozess,
 *                                      so hält er keine Sperre der Speicherschicht dauerhaft, z. B. beim Umschalten auf SQLite)
 *   php api/postausgang.php --pruefen  Zustandsprüfung für Docker: Rückgabe 0, wenn das letzte Lebenszeichen frisch ist
 *   php api/postausgang.php --umschluesseln | --entbinden
 *                                      hinterlegte Postfach-Passwörter von Format v1 auf v2 (an Server und Benutzer gebunden,
 *                                      app/api/mail.php) umstellen bzw. zurück auf v1 für einen Rückfall auf ein älteres Release –
 *                                      Teil von deploy/postfach-schluessel.sh umziehen bzw. zurueck
 */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
const WA_API = true;
const WA_CLI = true;   // fail()/respond() werfen eine Ausnahme statt den Prozess zu beenden (lib/kern.php)
ini_set('display_errors', '0');
ini_set('log_errors', '1');
date_default_timezone_set('Europe/Berlin');   // wie api/index.php: Uhrzeiten in E-Mails in deutscher Zeit

require __DIR__ . '/lib/laden.php';

if (in_array('--pruefen', $argv, true)) {
    $t = (int)(postausgang_stand()['t'] ?? 0);
    echo $t > time() - 180 ? "Postausgang: Lebenszeichen vor " . (time() - $t) . " s\n" : "Postausgang: kein frisches Lebenszeichen\n";
    exit($t > time() - 180 ? 0 : 1);
}
if (in_array('--umschluesseln', $argv, true) || in_array('--entbinden', $argv, true)) {
    $binden = in_array('--umschluesseln', $argv, true);
    $fehler = false;
    foreach (MAIL_KONTEN as $konto => $doc) {
        $erg = with_lock($doc, function () use ($doc, $binden) {
            $a = store_read($doc);
            $enc = is_array($a) ? (string)($a['passEnc'] ?? '') : '';
            if ($enc === '') return 'ohne Passwort';
            if (strpos($enc, $binden ? 'v1:' : 'v2:') !== 0) return $binden ? 'bereits gebunden' : 'bereits Format v1';
            $p = mail_decrypt($enc, $a);
            if ($p === null) return null;
            mail_key(false, $ort);
            if ($binden && $ort !== 'geheim') return null;   // gebunden wird nur mit dem Schlüssel im eigenen Ordner
            $a['passEnc'] = $binden ? mail_encrypt($p, $a) : mail_encrypt($p);
            store_write($doc, $a);
            return $binden ? 'an Server und Benutzer gebunden' : 'auf Format v1 zurückgestellt (für ältere Releases)';
        });
        if ($erg === null) $fehler = true;
        echo ($konto === 'intern' ? 'Postfach für interne E-Mails' : 'Postfach') . ': ' . ($erg ?? 'nicht entschlüsselbar – Schlüssel fehlt? Passwort im Eingabebereich neu eingeben') . "\n";
    }
    exit($fehler ? 1 : 0);
}
try {
    $r = postausgang_lauf();
    if ($r['erledigt'] || $r['wieder'] || $r['fehler']) {
        echo gmdate('Y-m-d H:i:s') . " Postausgang: {$r['erledigt']} erledigt, {$r['wieder']} erneut eingeplant, {$r['fehler']} fehlgeschlagen\n";
    }
} catch (Throwable $e) {
    store_rollback();
    fwrite(STDERR, gmdate('Y-m-d H:i:s') . ' Postausgang: ' . $e->getMessage() . "\n");
    exit(1);
}
