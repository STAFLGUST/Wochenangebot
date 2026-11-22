<?php
declare(strict_types=1);
/* Container-Import: ausgehende Abrufe fremder Dienste (Hafen Hamburg, Whisp) mit einer Gesamtfrist.
   Warum eine eigene Stelle: das Zeitlimit eines PHP-Stroms gilt nur je Schritt beim Verbinden und Lesen. Eine Gegenstelle,
   die tröpfelt statt zu antworten (überlasteter Dienst, Stelle im Netzweg, umgelenkte Namensauflösung), hielte einen
   Abruf deshalb beliebig lange offen und damit einen Webserver-Prozess belegt – mod_php bricht blockierende
   Lesevorgänge nicht ab, max_execution_time greift dort nicht. cURL legt mit CURLOPT_TIMEOUT eine einzige
   Wanduhr-Frist über Verbinden, Kopfzeilen und Rumpf zugleich.
   Zweitens meldet cURL eine abgebrochene Antwort als Fehler, statt den schon gelesenen Teil für vollständig zu halten:
   eine abgeschnittene Antwort wird so nie still der neue Stand – auch nicht bei stückweiser Antwort
   (Transfer-Encoding: chunked) ohne angekündigte Länge.
   Hinaus geht nur, was der Aufrufer mitgibt: keine Weiterleitungen, keine Cookies, nur die übergebenen Kopfzeilen. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_ABRUF_VERBINDEN = 8;   // Sekunden für den Verbindungsaufbau – Teil der Gesamtfrist, nie länger als sie

/* Eine Antwort holen. Liefert ['status' => HTTP-Status (0 = gar keine Antwort), 'roh' => Inhalt, 'fehler' => Kennung]:
   '' in Ordnung · 'netz' nicht erreichbar oder Frist um, bevor Kopfzeilen kamen · 'halb' Antwort brach ab oder die Frist
   war um · 'gross' mehr als $maxByte Inhalt. Bei jedem Fehler ist 'roh' leer – ein halber Inhalt wird nie ausgewertet. */
function ci_abruf(string $url, array $kopfzeilen, int $frist, int $maxByte, string $methode = 'GET', ?string $inhalt = null): array
{
    $roh = '';
    $gross = false;
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_CUSTOMREQUEST => $methode,
        CURLOPT_HTTPHEADER => array_merge($kopfzeilen, ['Expect:']),   // kein „100 Continue“: das wartet nur auf die Gegenstelle
        CURLOPT_FOLLOWLOCATION => false,
        CURLOPT_CONNECTTIMEOUT => max(1, min(CI_ABRUF_VERBINDEN, $frist)),
        CURLOPT_TIMEOUT => $frist,                 // Gesamtfrist über Verbinden, Kopfzeilen und Rumpf
        CURLOPT_NOSIGNAL => true,                  // keine Signale (Apache kann mit Fäden laufen)
        CURLOPT_WRITEFUNCTION => function ($ch, string $teil) use (&$roh, &$gross, $maxByte): int {
            if (strlen($roh) + strlen($teil) > $maxByte) { $gross = true; return 0; }   // 0 bricht den Abruf ab
            $roh .= $teil;
            return strlen($teil);
        },
    ]);
    if ($inhalt !== null) curl_setopt($ch, CURLOPT_POSTFIELDS, $inhalt);
    curl_exec($ch);
    $nr = curl_errno($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    curl_close($ch);
    if ($gross) return ['status' => $status, 'roh' => '', 'fehler' => 'gross'];
    if ($nr !== 0) return ['status' => $status, 'roh' => '', 'fehler' => $status === 0 ? 'netz' : 'halb'];
    return ['status' => $status, 'roh' => $roh, 'fehler' => ''];
}
