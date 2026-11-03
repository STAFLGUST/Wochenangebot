<?php
declare(strict_types=1);
/* Modul HR · E-Mails der Urlaubsverwaltung (Inhaber 03.11.2026). Versand über das interne Postfach (mail_cfg_intern).
   - Erinnerung „Resturlaub verfällt“: auf Knopfdruck der Personalstelle an alle Mitarbeiter im Urlaubsplan, bei denen
     Übertrag aus dem Vorjahr noch verfallen würde (Konto „verfaellt“ > 0).
   - Monatsübersicht: jedem Mitarbeiter im Urlaubsplan mit E-Mail-Adresse sein Urlaub des Vormonats und sein Stand im Jahr –
     automatisch einmal im Monat (Schalter, ab dem 1.) oder auf Knopfdruck.
   - Steuerberater: Excel-Übersicht (wie der Export) des Vormonats und des laufenden Monats an eine hinterlegte Adresse –
     automatisch am gewählten Tag (1.–28.) oder auf Knopfdruck.
   - Unentschuldigtes Fehlen (Art F, Inhaber 03.11.2026): beim Eintragen durch die Personalstelle (abwählbar) eine E-Mail an den
     Mitarbeiter mit seiner Urlaubsübersicht des Jahres und der Bitte um eine unverzügliche Erklärung per E-Mail; Antworten
     gehen an die Adresse der eintragenden Person (Reply-To), sonst an die Antwortadresse des Postfachs.
   - Testmodus: alle HR-E-Mails gehen nur an die Testadresse (Betreff mit „[Test …]“), z. B. zum Ausprobieren.
   Der automatische Versand wird von HR-Aufrufen angestoßen (hr_mail_anstossen: Urlaubsseite, Kalender, Verwaltung) und läuft
   nach der Antwort – kein Zeitplan auf dem Server nötig; der Monat wird vorher unter Sperre vermerkt (genau ein Versand).
   Gespeichert im eigenen Dokument hr-einstellungen: „mail“ {monat{an, stand}, test{an, adresse}, steuerberater{an, adresse,
   tag, stand}} und „mailVerlauf“ (letzte Versände). Krankheit steht nie in Mails an Mitarbeiter; die Excel-Datei an den
   Steuerberater enthält wie der Export alle genehmigten Abwesenheiten. Eingebunden von module/hr/urlaub.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const HR_MAIL_VERLAUF_MAX = 40;
const HR_STB_TAG_STANDARD = 5;

/* Gültige E-Mail-Adresse (eine, ohne Zeilenumbruch) oder '' */
function hr_mail_adresse($v): string
{
    $a = trim((string)$v);
    if ($a === '' || strlen($a) > 200 || preg_match('/[\r\n,;]/', $a) || !filter_var($a, FILTER_VALIDATE_EMAIL)) return '';
    return strtolower($a);
}

/* Einstellungen (fehlende Felder: aus) */
function hr_mail_einst(?array $d = null): array
{
    $d = $d ?? (store_read('hr-einstellungen') ?? []);
    $m = is_array($d['mail'] ?? null) ? $d['mail'] : [];
    $mo = is_array($m['monat'] ?? null) ? $m['monat'] : []; $te = is_array($m['test'] ?? null) ? $m['test'] : []; $st = is_array($m['steuerberater'] ?? null) ? $m['steuerberater'] : [];
    $ym = function ($v) { return is_string($v) && preg_match('/^\d{4}-\d{2}$/', $v) ? $v : ''; };
    $tag = (int)($st['tag'] ?? HR_STB_TAG_STANDARD);
    return ['monat' => ['an' => ($mo['an'] ?? false) === true, 'stand' => $ym($mo['stand'] ?? null)],
            'test' => ['an' => ($te['an'] ?? false) === true, 'adresse' => hr_mail_adresse($te['adresse'] ?? '')],
            'steuerberater' => ['an' => ($st['an'] ?? false) === true, 'adresse' => hr_mail_adresse($st['adresse'] ?? ''),
                                'tag' => $tag >= 1 && $tag <= 28 ? $tag : HR_STB_TAG_STANDARD, 'stand' => $ym($st['stand'] ?? null)]];
}

/* Monate relativ zu heute (deutsche Zeit des Servers): [Vormonat, laufender Monat] als „JJJJ-MM“ */
function hr_mail_monate(?DateTimeImmutable $jetzt = null): array
{
    $j = $jetzt ?? new DateTimeImmutable('now');
    return [$j->modify('first day of last month')->format('Y-m'), $j->format('Y-m')];
}
function hr_ym_text(string $ym): string { return HR_MONATE[(int)substr($ym, 5, 2)] . ' ' . substr($ym, 0, 4); }

/* Nächste automatische Termine (für die Anzeige) */
function hr_mail_naechste(array $m, ?DateTimeImmutable $jetzt = null): array
{
    $j = $jetzt ?? new DateTimeImmutable('now');
    [$vor, $dies] = hr_mail_monate($j);
    $monat = null;
    if ($m['monat']['an']) $monat = $m['monat']['stand'] < $vor ? $j->format('Y-m-d') : $j->modify('first day of next month')->format('Y-m-d');
    $stb = null;
    if ($m['steuerberater']['an']) {
        $tag = $m['steuerberater']['tag'];
        if ($m['steuerberater']['stand'] < $dies) $stb = (int)$j->format('j') >= $tag ? $j->format('Y-m-d') : $j->format('Y-m-') . sprintf('%02d', $tag);
        else $stb = $j->modify('first day of next month')->format('Y-m-') . sprintf('%02d', $tag);
    }
    return ['monat' => $monat, 'steuerberater' => $stb];
}

/* Mitarbeiter im Urlaubsplan mit Anmeldungskonto und E-Mail-Adresse: [[Person, Adresse], …] und Zahl ohne Adresse */
function hr_mail_empfaenger(): array
{
    $mail = [];
    foreach (users_load() as $u) $mail[(string)$u['id']] = hr_mail_adresse($u['email'] ?? '');
    $mit = []; $ohne = 0;
    foreach (hr_personal()['personen'] as $p) {
        if (!$p['aktiv'] || !empty($p['altbestand']) || $p['nutzer'] === null) continue;
        $a = $mail[$p['nutzer']] ?? '';
        if ($a === '') { $ohne++; continue; }
        $mit[] = [$p, $a];
    }
    return [$mit, $ohne];
}

/* Testmodus: Empfänger und Betreff umlenken */
function hr_mail_ziel(array $m, string $an, string $name, string $betreff): array
{
    if ($m['test']['an'] && $m['test']['adresse'] !== '') return [$m['test']['adresse'], '', '[Test – für ' . ($name !== '' ? $name : $an) . '] ' . $betreff];
    return [$an, $name, $betreff];
}

/* Gemeinsamer Rahmen der HR-Mails */
function hr_mail_rahmen(string $betreff, string $text, string $html): array
{
    global $CFG;
    $firma = (string)($CFG['company'] ?? '');
    $sig = "Ihre Personalstelle" . ($firma !== '' ? "\n$firma" : '');
    $fuss = 'Diese E-Mail kommt automatisch aus der Urlaubsverwaltung der STAFL-Plattform.';
    return [$betreff, $text . "\n\n$sig\n\n-- \n$fuss\n", mail_layout($betreff, $html, $sig, $fuss)];
}
function hr_mail_link(): string { return (string)(MODULE['hr']['oberflaechen']['intern']['adresse'] ?? ''); }
function hr_mail_knopf(): array
{
    $url = hr_mail_link();
    return [$url !== '' ? "\nUrlaubsverwaltung: $url" : '', $url !== '' ? mail_button($url, 'Zur Urlaubsverwaltung') : ''];
}
function hr_tage_text(float $n): string { $z = rtrim(rtrim(number_format($n, 1, ',', ''), '0'), ','); return $z . ' ' . (abs($n) == 1.0 ? 'Tag' : 'Tage'); }

/* Monatsübersicht einer Person: Urlaub (genehmigt) im Monat mit Arbeitstagen, dazu der Stand im Jahr. Nie Krankheit. */
function hr_mail_monat_inhalt(array $p, array $eintraege, string $ym): array
{
    $mv = $ym . '-01'; $mb = (new DateTimeImmutable($mv))->format('Y-m-t');
    $jahr = (int)substr($ym, 0, 4);
    $frei = hr_freie_tage($eintraege, $p['id']);
    $zeilen = []; $summe = 0;
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || $e['art'] !== 'U' || $e['status'] !== 'genehmigt' || $e['von'] > $mb || $e['bis'] < $mv) continue;
        $n = count(hr_tage($p, $e['von'], $e['bis'], $mv, $mb, $frei));
        if (!$n) continue;
        $zeilen[] = [max($e['von'], $mv), min($e['bis'], $mb), $n]; $summe += $n;
    }
    usort($zeilen, function ($a, $b) { return $a[0] <=> $b[0]; });
    $k = hr_konto($p, $eintraege, $jahr);
    $mon = hr_ym_text($ym);
    $vor = trim($p['vorname']) !== '' ? $p['vorname'] : hr_name($p);
    $betreff = "Ihr Urlaub im $mon";
    $liste = array_map(function ($z) { return hr_zeitraum_text($z[0], $z[1]) . ' (' . hr_tage_text((float)$z[2]) . ')'; }, $zeilen);
    $satz = $zeilen ? "im $mon hatten Sie " . hr_tage_text((float)$summe) . ' Urlaub:' : "im $mon hatten Sie keinen Urlaub.";
    $stand = "Ihr Urlaub $jahr: Anspruch " . hr_tage_text($k['anspruch']) . ($k['uebertrag'] != 0 ? ', Übertrag ' . hr_tage_text($k['uebertrag']) : '')
        . ', genommen ' . hr_tage_text((float)$k['genommen']) . ', geplant ' . hr_tage_text((float)$k['geplant']) . ' – Resturlaub ' . hr_tage_text($k['rest'])
        . ($k['beantragt'] ? ' (davon ' . hr_tage_text((float)$k['beantragt']) . ' beantragt)' : '') . '.';
    $verfall = $k['verfaellt'] > 0 ? hr_tage_text($k['verfaellt']) . ' Resturlaub aus dem Vorjahr ' . ($k['verfaellt'] == 1.0 ? 'verfällt' : 'verfallen') . ' am ' . hr_de($k['frist']) . ', wenn Sie ' . ($k['verfaellt'] == 1.0 ? 'ihn' : 'sie') . ' bis dahin nicht nehmen.' : '';
    [$lt, $lh] = hr_mail_knopf();
    $text = "Hallo $vor,\n\n$satz" . ($liste ? "\n- " . implode("\n- ", $liste) : '') . "\n\n$stand" . ($verfall !== '' ? "\n$verfall" : '') . $lt;
    $html = '<p style="margin:0 0 14px;">Hallo ' . mail_h($vor) . ',</p><p style="margin:0 0 8px;">' . mail_h($satz) . '</p>'
        . ($liste ? '<ul style="margin:0 0 14px;padding-left:20px;">' . implode('', array_map(function ($l) { return '<li>' . mail_h($l) . '</li>'; }, $liste)) . '</ul>' : '')
        . '<p style="margin:0 0 14px;">' . mail_h($stand) . '</p>'
        . ($verfall !== '' ? '<p style="margin:0 0 14px;padding:10px 12px;background:#fbeee0;border-radius:8px;"><strong>' . mail_h($verfall) . '</strong></p>' : '') . $lh;
    return hr_mail_rahmen($betreff, $text, $html);
}

/* Erinnerung „Resturlaub verfällt“ */
function hr_mail_erinnerung_inhalt(array $p, array $k): array
{
    $vor = trim($p['vorname']) !== '' ? $p['vorname'] : hr_name($p);
    $eins = $k['verfaellt'] == 1.0;
    $betreff = 'Erinnerung: Ihr Resturlaub verfällt am ' . hr_de($k['frist']);
    $satz = hr_tage_text($k['verfaellt']) . ' Resturlaub aus dem Vorjahr ' . ($eins ? 'verfällt' : 'verfallen') . ' am ' . hr_de($k['frist']) . ', wenn Sie ' . ($eins ? 'ihn' : 'sie') . ' bis dahin nicht nehmen.';
    $bitte = 'Bitte beantragen Sie Ihren Urlaub rechtzeitig. Ihr Resturlaub insgesamt: ' . hr_tage_text($k['rest']) . '.';
    [$lt, $lh] = hr_mail_knopf();
    $text = "Hallo $vor,\n\n$satz\n$bitte$lt";
    $html = '<p style="margin:0 0 14px;">Hallo ' . mail_h($vor) . ',</p><p style="margin:0 0 14px;padding:10px 12px;background:#fbeee0;border-radius:8px;"><strong>' . mail_h($satz) . '</strong></p>'
        . '<p style="margin:0 0 14px;">' . mail_h($bitte) . '</p>' . $lh;
    return hr_mail_rahmen($betreff, $text, $html);
}

/* Versand: Jobs senden, Verlauf und Protokoll schreiben. Rückgabe: Zusammenfassung */
function hr_mail_versenden(array $jobs, string $art, string $wie, ?array $me, array $zusatz = [], string $antwortAn = ''): array
{
    $cfg = mail_cfg_intern();
    if (!$cfg) throw new RuntimeException('Der E-Mail-Versand ist noch nicht eingerichtet (Zugangsdaten des Postfachs in .env auf dem Server).');
    if ($antwortAn !== '') $cfg['replyTo'] = $antwortAn;
    $res = $jobs ? mail_send_many($cfg, $jobs) : [];
    $ok = 0; $fehler = [];
    foreach ($jobs as $k => $j) { if (!empty($res[$k]['ok'])) $ok++; else $fehler[] = $j['to'] . ': ' . ($res[$k]['error'] ?? 'Versandfehler'); }
    $eintrag = ['t' => now(), 'art' => $art, 'wie' => $wie, 'gesendet' => $ok, 'fehler' => count($fehler), 'by' => $me ? (string)$me['name'] : 'automatisch'] + $zusatz;
    with_lock('hr-einstellungen', function () use ($eintrag) {
        $d = store_read('hr-einstellungen') ?? [];
        $v = is_array($d['mailVerlauf'] ?? null) ? $d['mailVerlauf'] : [];
        array_unshift($v, $eintrag);
        $d['mailVerlauf'] = array_slice($v, 0, HR_MAIL_VERLAUF_MAX);
        store_write('hr-einstellungen', $d);
    });
    $namen = ['monat' => 'Monatsübersicht', 'erinnerung' => 'Erinnerung „Resturlaub verfällt“', 'steuerberater' => 'Übersicht an den Steuerberater',
              'fehlen' => 'E-Mail zur Abwesenheit' . (isset($zusatz['name']) ? ' an ' . $zusatz['name'] : '') . ' (Bitte um Erklärung)'];
    audit('hr', 'HR: ' . ($namen[$art] ?? $art) . ($wie === 'automatisch' ? ' (automatisch)' : '') . (!empty($zusatz['test']) ? ' (Testmodus)' : '') . ': ' . $ok . ' gesendet'
        . ($fehler ? ', ' . count($fehler) . ' nicht zugestellt' : ''), [], $me ?? ['username' => 'system', 'name' => 'System (automatisch)', 'role' => '']);
    return $eintrag + ['fehlerText' => array_slice($fehler, 0, 5)];
}

/* Monatsübersicht für „JJJJ-MM“ an alle Mitarbeiter mit Adresse (Testmodus: an die Testadresse) */
function hr_monat_senden(string $ym, string $wie, ?array $me): array
{
    $m = hr_mail_einst();
    [$mit, $ohne] = hr_mail_empfaenger();
    $abw = hr_abwesenheiten()['eintraege'];
    $jobs = [];
    foreach ($mit as [$p, $an]) {
        [$betreff, $text, $html] = hr_mail_monat_inhalt($p, $abw, $ym);
        [$to, $name, $betreff] = hr_mail_ziel($m, $an, hr_name($p), $betreff);
        $jobs[] = ['to' => $to, 'name' => $name, 'subject' => $betreff, 'text' => $text, 'html' => $html];
    }
    return hr_mail_versenden($jobs, 'monat', $wie, $me, ['monat' => $ym, 'ohneAdresse' => $ohne, 'test' => $m['test']['an']]);
}

/* Erinnerung an alle, bei denen im laufenden Jahr Übertrag verfallen würde */
function hr_erinnerung_kandidaten(): array
{
    $abw = hr_abwesenheiten()['eintraege']; $jahr = (int)date('Y');
    [$mit, $ohne] = hr_mail_empfaenger();
    $mail = []; foreach ($mit as [$p, $a]) $mail[$p['id']] = $a;
    $out = []; $ohneAdresse = 0;
    foreach (hr_personal()['personen'] as $p) {
        if (!$p['aktiv'] || !empty($p['altbestand'])) continue;
        $k = hr_konto($p, $abw, $jahr);
        if (!($k['verfaellt'] > 0)) continue;
        if (!isset($mail[$p['id']])) { $ohneAdresse++; continue; }
        $out[] = [$p, $mail[$p['id']], $k];
    }
    return [$out, $ohneAdresse];
}
function hr_erinnerung_senden(array $me): array
{
    $m = hr_mail_einst();
    [$liste, $ohne] = hr_erinnerung_kandidaten();
    $jobs = [];
    foreach ($liste as [$p, $an, $k]) {
        [$betreff, $text, $html] = hr_mail_erinnerung_inhalt($p, $k);
        [$to, $name, $betreff] = hr_mail_ziel($m, $an, hr_name($p), $betreff);
        $jobs[] = ['to' => $to, 'name' => $name, 'subject' => $betreff, 'text' => $text, 'html' => $html];
    }
    return hr_mail_versenden($jobs, 'erinnerung', 'manuell', $me, ['ohneAdresse' => $ohne, 'test' => $m['test']['an']]);
}

/* Unentschuldigtes Fehlen: Text mit Zeitraum, Bitte um unverzügliche Erklärung per E-Mail und Urlaubsübersicht des Jahres
   (Konto und genehmigte/beantragte Urlaubszeiträume). Keine Krankheit, keine Notizen. */
function hr_mail_fehlen_inhalt(array $p, array $e, array $eintraege): array
{
    $jahr = (int)substr($e['von'], 0, 4);
    $k = hr_konto($p, $eintraege, $jahr);
    $frei = hr_freie_tage($eintraege, $p['id']);
    $urlaub = [];
    foreach ($eintraege as $x) {
        if ($x['person'] !== $p['id'] || $x['art'] !== 'U' || !in_array($x['status'], HR_AKTIV, true) || $x['bis'] < "$jahr-01-01" || $x['von'] > "$jahr-12-31") continue;
        $n = count(hr_tage($p, $x['von'], $x['bis'], "$jahr-01-01", "$jahr-12-31", $frei));
        if ($n) $urlaub[] = [$x['von'], hr_zeitraum_text($x['von'], $x['bis']) . ' (' . hr_tage_text((float)$n) . ($x['status'] === 'beantragt' ? ', beantragt' : '') . ')'];
    }
    usort($urlaub, function ($a, $b) { return $a[0] <=> $b[0]; });
    $urlaub = array_column($urlaub, 1);
    $vor = trim($p['vorname']) !== '' ? $p['vorname'] : hr_name($p);
    $wann = $e['von'] === $e['bis'] ? 'am ' . hr_de($e['von']) : 'vom ' . hr_de($e['von']) . ' bis ' . hr_de($e['bis']);
    $betreff = 'Abwesenheit ' . $wann . ' – bitte um Rückmeldung';
    $satz = "Sie sind $wann nicht zur Arbeit erschienen. Eine Entschuldigung liegt uns nicht vor.";
    $bitte = 'Bitte teilen Sie uns unverzüglich per E-Mail mit, weshalb Sie nicht zur Arbeit erschienen sind – antworten Sie dazu einfach auf diese E-Mail.';
    $stand = "Ihre Urlaubsübersicht $jahr: Anspruch " . hr_tage_text($k['anspruch']) . ($k['uebertrag'] != 0 ? ', Übertrag ' . hr_tage_text($k['uebertrag']) : '')
        . ', genommen ' . hr_tage_text((float)$k['genommen']) . ', geplant ' . hr_tage_text((float)$k['geplant']) . ' – Resturlaub ' . hr_tage_text($k['rest'])
        . ($k['beantragt'] ? ' (davon ' . hr_tage_text((float)$k['beantragt']) . ' beantragt)' : '') . '.';
    [$lt, $lh] = hr_mail_knopf();
    $text = "Hallo $vor,\n\n$satz\n$bitte\n\n$stand" . ($urlaub ? "\nIhr Urlaub $jahr:\n- " . implode("\n- ", $urlaub) : "\nIn $jahr ist noch kein Urlaub eingetragen.") . $lt;
    $html = '<p style="margin:0 0 14px;">Hallo ' . mail_h($vor) . ',</p><p style="margin:0 0 10px;">' . mail_h($satz) . '</p>'
        . '<p style="margin:0 0 14px;padding:10px 12px;background:#fbeee0;border-radius:8px;"><strong>' . mail_h($bitte) . '</strong></p>'
        . '<p style="margin:0 0 8px;">' . mail_h($stand) . '</p>'
        . ($urlaub ? '<p style="margin:0 0 4px;">Ihr Urlaub ' . $jahr . ':</p><ul style="margin:0 0 14px;padding-left:20px;">' . implode('', array_map(function ($l) { return '<li>' . mail_h($l) . '</li>'; }, $urlaub)) . '</ul>'
                   : '<p style="margin:0 0 14px;">In ' . $jahr . ' ist noch kein Urlaub eingetragen.</p>') . $lh;
    return hr_mail_rahmen($betreff, $text, $html);
}
/* E-Mail nach dem Eintragen von unentschuldigtem Fehlen. Rückgabe {gesendet: bool, an, grund} – ein Fehler beim Versand
   macht den Eintrag nicht ungültig. */
function hr_fehlen_mail(array $p, array $e, array $eintraege, array $me): array
{
    $an = '';
    if ($p['nutzer'] !== null) foreach (users_load() as $u) if ((string)$u['id'] === $p['nutzer']) $an = hr_mail_adresse($u['email'] ?? '');
    if ($an === '') return ['gesendet' => false, 'an' => '', 'grund' => 'Für ' . hr_name($p) . ' ist keine E-Mail-Adresse hinterlegt (Verwaltung → Mitarbeiter).'];
    if (!mail_cfg_intern()) return ['gesendet' => false, 'an' => $an, 'grund' => 'Der E-Mail-Versand ist auf dem Server noch nicht eingerichtet.'];
    $m = hr_mail_einst();
    [$betreff, $text, $html] = hr_mail_fehlen_inhalt($p, $e, $eintraege);
    [$to, $name, $betreff] = hr_mail_ziel($m, $an, hr_name($p), $betreff);
    try {
        $r = hr_mail_versenden([['to' => $to, 'name' => $name, 'subject' => $betreff, 'text' => $text, 'html' => $html]], 'fehlen', 'manuell', $me,
                               ['name' => hr_name($p), 'test' => $m['test']['an']], hr_mail_adresse($me['email'] ?? ''));
    } catch (RuntimeException $ex) { return ['gesendet' => false, 'an' => $to, 'grund' => $ex->getMessage()]; }
    return ['gesendet' => $r['gesendet'] === 1, 'an' => $to, 'test' => $m['test']['an'], 'grund' => $r['gesendet'] === 1 ? '' : ($r['fehlerText'][0] ?? 'Versandfehler')];
}

/* Excel-Übersicht des Vormonats und des laufenden Monats an den Steuerberater */
function hr_stb_senden(string $wie, ?array $me): array
{
    global $CFG;
    $m = hr_mail_einst();
    $an = $m['steuerberater']['adresse'];
    if ($an === '') throw new RuntimeException('Bitte zuerst die E-Mail-Adresse des Steuerberaters eintragen und speichern.');
    [$vor, $dies] = hr_mail_monate();
    $monate = array_map(function ($ym) { return hr_export_monat((int)substr($ym, 0, 4), (int)substr($ym, 5, 2)); }, [$vor, $dies]);
    $datei = sprintf('Urlaub_%s_bis_%s.xlsx', $vor, $dies);
    $firma = (string)($CFG['company'] ?? '');
    $zeitraum = hr_ym_text($vor) . ' und ' . hr_ym_text($dies);
    $betreff = "Urlaubs- und Abwesenheitsübersicht $zeitraum" . ($firma !== '' ? " – $firma" : '');
    $text = "Sehr geehrte Damen und Herren,\n\nanbei die Übersicht der Urlaubs- und Abwesenheitstage für $zeitraum als Excel-Datei ($datei).";
    $html = '<p style="margin:0 0 14px;">Sehr geehrte Damen und Herren,</p><p style="margin:0 0 14px;">anbei die Übersicht der Urlaubs- und Abwesenheitstage für '
        . mail_h($zeitraum) . ' als Excel-Datei (' . mail_h($datei) . ').</p>';
    [$betreff, $text, $html] = hr_mail_rahmen($betreff, $text, $html);
    [$to, $name, $betreff] = hr_mail_ziel($m, $an, 'Steuerberater', $betreff);
    $job = ['to' => $to, 'name' => $name, 'subject' => $betreff, 'text' => $text, 'html' => $html,
            'anhaenge' => [['name' => $datei, 'type' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'data' => hr_xlsx($monate)]]];
    return hr_mail_versenden([$job], 'steuerberater', $wie, $me, ['monat' => "$vor/$dies", 'an' => $an, 'test' => $m['test']['an']]);
}

/* Automatischer Versand: von HR-Aufrufen angemeldeter Mitarbeiter angestoßen. Fällig ist die Monatsübersicht ab dem 1. für
   den Vormonat, die Steuerberater-Übersicht ab dem eingestellten Tag einmal im Monat. Der Monat wird unter Sperre vermerkt
   (genau ein Versand, auch bei gleichzeitigen Aufrufen), versendet wird nach der Antwort. Fehler landen im Fehlerprotokoll. */
function hr_mail_anstossen(): void
{
    try {
        $m = hr_mail_einst();
        [$vor, $dies] = hr_mail_monate();
        $tag = (int)date('j');
        $faellig = function (array $m) use ($vor, $dies, $tag) {
            return [$m['monat']['an'] && $m['monat']['stand'] < $vor,
                    $m['steuerberater']['an'] && $m['steuerberater']['adresse'] !== '' && $tag >= $m['steuerberater']['tag'] && $m['steuerberater']['stand'] < $dies];
        };
        [$a, $b] = $faellig($m);
        if (!$a && !$b) return;
        if (mail_cfg_intern() === null) return;   // ohne Postfach nichts vermerken – der Versand kommt, sobald es eingerichtet ist
        [$a, $b] = with_lock('hr-einstellungen', function () use ($faellig, $vor, $dies) {
            $d = store_read('hr-einstellungen') ?? [];
            [$a, $b] = $faellig(hr_mail_einst($d));
            if (!$a && !$b) return [false, false];
            $mail = is_array($d['mail'] ?? null) ? $d['mail'] : [];
            if ($a) $mail['monat'] = array_merge(is_array($mail['monat'] ?? null) ? $mail['monat'] : [], ['stand' => $vor]);
            if ($b) $mail['steuerberater'] = array_merge(is_array($mail['steuerberater'] ?? null) ? $mail['steuerberater'] : [], ['stand' => $dies]);
            $d['mail'] = $mail;
            store_write('hr-einstellungen', $d);
            return [$a, $b];
        });
        if (!$a && !$b) return;
        register_shutdown_function(function () use ($a, $b, $vor) {
            try {
                if (!empty($GLOBALS['store_tx'])) return;
                if (function_exists('fastcgi_finish_request')) fastcgi_finish_request();
                ignore_user_abort(true);
                @set_time_limit(180);
                if ($a) hr_monat_senden($vor, 'automatisch', null);
                if ($b) hr_stb_senden('automatisch', null);
            } catch (Throwable $e) {
                error_log('[wochenangebot] HR-Mails: ' . $e->getMessage());
            }
        });
    } catch (Throwable $e) {
        error_log('[wochenangebot] HR-Mails prüfen: ' . $e->getMessage());
    }
}

/* Einstellungen speichern (Verwaltung → Urlaub). Einschalten setzt den Stand so, dass der erste automatische Versand
   erst zum nächsten Termin kommt (Monatsübersicht: nächster Monatsbeginn; Steuerberater: ist der Tag schon vorbei, nächster
   Monat). Rückgabe: [alte, neue Einstellungen]. */
function hr_mail_speichern(array $b): array
{
    $bool = function ($v, string $was) { if (!is_bool($v)) throw new InvalidArgumentException("$was: bitte ja oder nein angeben."); return $v; };
    $adresse = function ($v, string $was) {
        if (!is_string($v) && $v !== null) throw new InvalidArgumentException("$was: bitte eine E-Mail-Adresse angeben.");
        $t = trim((string)$v);
        if ($t === '') return '';
        $a = hr_mail_adresse($t);
        if ($a === '') throw new InvalidArgumentException("$was: „" . mb_substr($t, 0, 60) . "“ ist keine gültige E-Mail-Adresse (genau eine Adresse).");
        return $a;
    };
    $mo = is_array($b['monat'] ?? null) ? $b['monat'] : []; $te = is_array($b['test'] ?? null) ? $b['test'] : []; $st = is_array($b['steuerberater'] ?? null) ? $b['steuerberater'] : [];
    $monatAn = $bool($mo['an'] ?? false, 'Monatsübersicht automatisch');
    $testAn = $bool($te['an'] ?? false, 'Testmodus');
    $testAdr = $adresse($te['adresse'] ?? '', 'Testadresse');
    if ($testAn && $testAdr === '') throw new InvalidArgumentException('Testmodus: bitte die Testadresse eintragen.');
    $stbAn = $bool($st['an'] ?? false, 'Steuerberater automatisch');
    $stbAdr = $adresse($st['adresse'] ?? '', 'E-Mail-Adresse des Steuerberaters');
    if ($stbAn && $stbAdr === '') throw new InvalidArgumentException('Steuerberater automatisch: bitte die E-Mail-Adresse des Steuerberaters eintragen.');
    $tag = $st['tag'] ?? HR_STB_TAG_STANDARD;
    if (!is_int($tag) || $tag < 1 || $tag > 28) throw new InvalidArgumentException('Versandtag für den Steuerberater: bitte einen Tag von 1 bis 28 wählen.');
    return with_lock('hr-einstellungen', function () use ($monatAn, $testAn, $testAdr, $stbAn, $stbAdr, $tag) {
        $d = store_read('hr-einstellungen') ?? [];
        $alt = hr_mail_einst($d);
        [$vor, $dies] = hr_mail_monate();
        $standMonat = $alt['monat']['stand'];
        if ($monatAn && !$alt['monat']['an']) $standMonat = max($standMonat, $vor);
        $standStb = $alt['steuerberater']['stand'];
        if ($stbAn && !$alt['steuerberater']['an'] && (int)date('j') >= $tag) $standStb = max($standStb, $dies);
        $d['mail'] = ['monat' => ['an' => $monatAn, 'stand' => $standMonat], 'test' => ['an' => $testAn, 'adresse' => $testAdr],
                      'steuerberater' => ['an' => $stbAn, 'adresse' => $stbAdr, 'tag' => $tag, 'stand' => $standStb]];
        $d['rev'] = (int)($d['rev'] ?? 0) + 1;
        store_write('hr-einstellungen', $d);
        return [$alt, hr_mail_einst($d)];
    });
}

/* Für Verwaltung → Urlaub: Einstellungen, Vorschau (Empfänger), nächste Termine, Verlauf, Postfach eingerichtet? */
function hr_mail_aus(): array
{
    $d = store_read('hr-einstellungen') ?? [];
    $m = hr_mail_einst($d);
    [$mit, $ohne] = hr_mail_empfaenger();
    [$erinnerung, $erinnerungOhne] = hr_erinnerung_kandidaten();
    return ['einst' => $m, 'naechste' => hr_mail_naechste($m), 'empfaenger' => count($mit), 'ohneAdresse' => $ohne,
            'erinnerung' => count($erinnerung), 'erinnerungOhneAdresse' => $erinnerungOhne, 'postfach' => mail_cfg_intern() !== null,
            'monate' => hr_mail_monate(), 'verlauf' => array_slice(is_array($d['mailVerlauf'] ?? null) ? $d['mailVerlauf'] : [], 0, 15)];
}
