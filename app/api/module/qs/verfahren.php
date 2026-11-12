<?php
declare(strict_types=1);
/* QM-System · Verfahrensdokumentation nach GoBD (Reiter „Verfahrensdoku“ der Oberfläche qs.intern, Aktionen qs_verfahren*
   in app/api/aktionen/qs.php; wird nur von diesen Aktionen geladen). Export als PDF/ZIP: module/qs/verfahren-export.php.

   Wozu: Die GoBD (BMF-Schreiben vom 28.11.2019 mit späteren Änderungen, Rz. 151–155) verlangen eine
   Verfahrensdokumentation, aus der Inhalt, Aufbau, Ablauf und Ergebnisse des DV-Verfahrens vollständig und schlüssig
   hervorgehen – in der Regel allgemeine Beschreibung, Anwenderdokumentation, technische Systemdokumentation und
   Betriebsdokumentation (Rz. 153), dazu das interne Kontrollsystem (Rz. 100–102). Sie ist bei Änderungen zu versionieren,
   mit nachvollziehbarer Änderungshistorie, und so lange aufzubewahren wie die Unterlagen, die sie erklärt (Rz. 154).
   Eine Gliederung ist nicht vorgeschrieben; die fünf Teile hier (QS_VF_TEILE) folgen der üblichen Einteilung.
   Die Inhalte schreibt das Unternehmen – die Mustergliederung (qs_vf_muster) liefert nur Überschriften und Fragen.

   Bewusst schlank (Auftrag des Inhabers 12.11.2026: kompakt, auch in der Pflege, aber formal belastbar):
     - 13 Abschnitte im Muster; Abschnitte verweisen auf vorhandene QM-Dokumente, statt Text doppelt zu pflegen
     - je Abschnitt nur „fertig“ ja/nein; kein Änderungsvermerk je Abschnitt – die Änderungshistorie entsteht bei der
       Freigabe von selbst (Vergleich mit der vorigen Fassung) plus eine Zeile Anlass
   Aufbau (Dokument „qs-verfahren“, Eigentümer qs; alle Schreibvorgänge unter der Sperre „qs-dokumente“):
     { rev, liste: [ Dokumentation ] } – je Unternehmen eine Dokumentation
     Dokumentation: id, titel, gesellschaft, verantwortlich (Kürzel), rev (zählt bei jeder Änderung), kopfRev,
       abschnitte[]  id, teil, pos, titel, text, hinweis (Frage aus dem Muster), systeme[] (Kennungen), verweise[] (Text
                     wie im Handbuch: „2.5-A01 Rechnungsbearbeitung“), zustaendig (Kürzel), fertig, rev
       systeme[]     IT-Systeme: id, name, art, zweck, anbieter, betrieb, ort, zustaendig, sicherung, schnittstellen,
                     seit, bis (außer Betrieb), rev
       fassungen[]   nr, datum (Freigabe), gueltigAb, grund (Anlass), freigegeben {t, von, vonId}, inhalt (Schnappschuss),
                     aenderungen[] (Textzeilen: was sich gegenüber der vorigen Fassung geändert hat)
       pruefungen[]  „ohne Änderung überprüft“: datum, fassung (Nummer der überprüften Fassung), t, von, vonId, notiz
   Regeln:
     - Eine Fassung ist ein unveränderlicher Schnappschuss (GR-106): Texte, IT-Systeme, Namen zu den Kürzeln und zu
       jedem verknüpften QM-Dokument die an diesem Tag gültige Version mit Datum. Fassungen werden nie geändert oder
       gelöscht; eine Dokumentation mit Fassung lässt sich nicht löschen.
     - Freigeben nur, wenn alle Abschnitte „fertig“ sind, Inhalt haben (Text oder verknüpftes QM-Dokument) und sich
       seit der letzten Fassung etwas geändert hat (qs_vf_abweichung – auch eine neue Version eines verknüpften
       QM-Dokuments zählt). „Gültig ab“ liegt nie vor der vorigen Fassung.
     - Der Arbeitsstand (Entwurf der nächsten Fassung) darf frei geändert werden; ein IT-System, das in einer Fassung
       steht, wird nicht gelöscht, sondern „außer Betrieb“ gesetzt.
     - Überprüfung: QS_VF_UEBERPRUEFUNG_MONATE nach der letzten Fassung bzw. „ohne Änderung überprüft“ fällig.
   Gelesen: qs-dokumente (Nummer, Titel, gültige Version) und Personen aus qs-stamm – beides eigene Dokumente des Moduls.
   Gespeicherte Felder, die diese Fassung nicht kennt, bleiben erhalten (GR-006).
   Rechte (GR-103, sensibel – einzeln freizugeben): qs.verfahren_sehen, qs.verfahren_bearbeiten, qs.verfahren_freigeben. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const QS_VF_DOKUMENT = 'qs-verfahren';
const QS_VF_TEILE = ['allgemein' => 'Allgemeine Beschreibung', 'anwender' => 'Anwenderdokumentation', 'technik' => 'Technische Systemdokumentation',
                     'betrieb' => 'Betriebsdokumentation', 'iks' => 'Internes Kontrollsystem'];
const QS_VF_SYSTEM_ART = ['haupt' => 'Hauptsystem (Buchführung)', 'vor' => 'Vorsystem', 'neben' => 'Nebensystem', 'archiv' => 'Archiv / Ablage'];
const QS_VF_BETRIEB = ['lokal' => 'Im Haus', 'rz' => 'Rechenzentrum / Dienstleister', 'cloud' => 'Cloud-Dienst'];
const QS_VF_KOPF = ['titel', 'gesellschaft', 'verantwortlich'];
const QS_VF_SYSTEM_INHALT = ['name', 'art', 'zweck', 'anbieter', 'betrieb', 'ort', 'zustaendig', 'sicherung', 'schnittstellen', 'seit', 'bis'];
const QS_VF_UEBERPRUEFUNG_MONATE = 12;
const QS_VF_MAX_DOKUS = 20;
const QS_VF_MAX_ABSCHNITTE = 100;
const QS_VF_MAX_SYSTEME = 100;
const QS_VF_MAX_FASSUNGEN = 200;
const QS_VF_MAX_PRUEFUNGEN = 200;
const QS_VF_MAX_FASSUNG_BYTES = 1500000;   // ein Schnappschuss als JSON

/* Mustergliederung: [Teil, Überschrift, Frage]. Nur Überschriften und Fragen – die Antworten schreibt das Unternehmen. */
function qs_vf_muster(): array
{
    return [
        ['allgemein', 'Unternehmen, Organisation und Geltungsbereich', 'Wer ist das Unternehmen (Firma, Rechtsform, Sitz, Tätigkeit)? Was wird im Haus erfasst und gebucht, was übernimmt der Steuerberater? Für welche Gesellschaft und ab wann gilt diese Dokumentation, wer ist verantwortlich?'],
        ['allgemein', 'Belegfluss im Überblick und Aufbewahrung', 'Wie fließen die Belege von der Entstehung bis zur Buchung und Ablage – in welchen Systemen? Was wird wo und wie lange aufbewahrt (Papier, elektronisch)? Die Fristen mit dem Steuerberater abstimmen.'],
        ['anwender', 'Eingangsrechnungen', 'Weg einer Eingangsrechnung, auch als E-Rechnung: Eingang, sachliche und rechnerische Prüfung, Freigabe, Buchung, Zahlung, Ablage. Wer macht welchen Schritt, in welchem System?'],
        ['anwender', 'Ausgangsrechnungen und Gutschriften', 'Wie entsteht eine Rechnung (Auftrag, Lieferschein, Warenwirtschaft)? Wer erstellt und versendet sie – auch als E-Rechnung –, wie werden Rechnungsnummern vergeben, wie werden Gutschriften und Korrekturen behandelt?'],
        ['anwender', 'Zahlungsverkehr, Bank und Kasse', 'Wer erstellt Zahlungen, wer gibt sie frei? Wie gelangen Kontoauszüge in die Buchführung? Gibt es eine Kasse oder Bargeschäfte – wenn ja, wie wird täglich aufgezeichnet; wenn nein, das kurz festhalten.'],
        ['anwender', 'Warenwirtschaft, Bestände und Inventur', 'Wie werden Wareneingang, Bestand und Warenausgang erfasst? Wie läuft die Inventur ab und wie gelangen die Werte in die Buchführung?'],
        ['anwender', 'Belegablage und Übergabe an Steuerberater und Lohnbüro', 'Wie werden Papierbelege erfasst (scannen) und abgelegt – bleibt das Original erhalten? Wo liegen Geschäftsbriefe und E-Mails zu einem Vorgang? Welche Daten und Belege gehen wann und auf welchem Weg an Steuerberater und Lohnbüro?'],
        ['technik', 'Systeme, Schnittstellen und Stammdaten', 'Die einzelnen Systeme stehen in der Liste „IT-Systeme“. Hier beschreiben: Zwischen welchen Systemen fließen Daten (Richtung, Inhalt, Rhythmus) und wie wird die Übertragung geprüft? Wo werden Stammdaten gepflegt und Änderungen protokolliert?'],
        ['technik', 'Archivierung, Unveränderbarkeit und Datenzugriff', 'Wo und in welchem Format werden Belege und Daten elektronisch aufbewahrt? Wodurch ist sichergestellt, dass sie nicht unbemerkt geändert oder gelöscht werden? Wie werden bei einer Außenprüfung Daten bereitgestellt, wer ist Ansprechpartner?'],
        ['betrieb', 'Berechtigungen, Datensicherung und Notbetrieb', 'Wie werden Benutzer angelegt, geändert und gesperrt, wer vergibt Rechte? Was wird wie oft wohin gesichert und wie wird die Wiederherstellung geprobt? Was geschieht bei Ausfall eines Systems?'],
        ['betrieb', 'Änderungen an Systemen und Dienstleister', 'Wie werden Updates und Systemwechsel geplant, getestet, freigegeben und festgehalten – und wie bleiben Altdaten lesbar? Welche Aufgaben sind ausgelagert (Rechenzentrum, Cloud, Steuerberater, Lohnbüro), welche Verträge liegen vor?'],
        ['iks', 'Kontrollen', 'Welche Kontrollen gibt es: Zugriffsschutz, Trennung von Aufgaben (z. B. Bestellen, Prüfen, Zahlen), Vier-Augen-Freigaben, Prüfungen gegen Fehleingaben, regelmäßige Abstimmungen (Bank, offene Posten, Bestand)? Wer macht sie, wie werden sie nachgewiesen?'],
        ['iks', 'Überwachung und Aktualisierung dieser Dokumentation', 'Wer prüft, ob die beschriebenen Verfahren eingehalten werden? Wann wird diese Dokumentation überprüft und bei welchen Anlässen sofort angepasst (neues System, geänderter Ablauf)?'],
    ];
}

/* ---------- Lesen und Ordnen ---------- */
/* Gespeicherte Dokumentation mit allen Listen und Feldern (unvollständige Einträge bleiben lesbar, GR-006) */
function qs_vf_normal(array $d): array
{
    foreach (['abschnitte', 'systeme', 'fassungen', 'pruefungen'] as $f) $d[$f] = is_array($d[$f] ?? null) ? array_values($d[$f]) : [];
    foreach (QS_VF_KOPF as $f) $d[$f] = (string)($d[$f] ?? '');
    foreach ($d['abschnitte'] as &$a) {
        $a['systeme'] = is_array($a['systeme'] ?? null) ? array_values($a['systeme']) : [];
        $a['verweise'] = is_array($a['verweise'] ?? null) ? array_values($a['verweise']) : [];
        foreach (['teil', 'titel', 'text', 'hinweis', 'zustaendig'] as $f) $a[$f] = (string)($a[$f] ?? '');
        $a['fertig'] = !empty($a['fertig']);
    }
    unset($a);
    foreach ($d['systeme'] as &$s) foreach (QS_VF_SYSTEM_INHALT as $f) $s[$f] = (string)($s[$f] ?? '');
    unset($s);
    return $d;
}
function qs_vf_sortieren(array &$abschnitte): void
{
    $rang = array_flip(array_keys(QS_VF_TEILE));
    usort($abschnitte, function ($a, $b) use ($rang) { return [$rang[$a['teil']] ?? 99, (int)($a['pos'] ?? 0)] <=> [$rang[$b['teil']] ?? 99, (int)($b['pos'] ?? 0)]; });
}
/* Nummern „<Teil>.<lfd. Nr.>“ für eine sortierte Liste: Kennung → Nummer */
function qs_vf_nummern(array $sortiert): array
{
    $rang = array_flip(array_keys(QS_VF_TEILE));
    $out = []; $n = [];
    foreach ($sortiert as $a) {
        if (!isset($rang[$a['teil']])) continue;
        $n[$a['teil']] = ($n[$a['teil']] ?? 0) + 1;
        $out[$a['id']] = ($rang[$a['teil']] + 1) . '.' . $n[$a['teil']];
    }
    return $out;
}
function qs_vf_naechste_pos(array $abschnitte, string $teil): int
{
    $pos = 0;
    foreach ($abschnitte as $x) if (($x['teil'] ?? '') === $teil) $pos = max($pos, (int)($x['pos'] ?? 0));
    return $pos + 1;
}
/* Index eines Eintrags (Abschnitt, System) in einer Liste der Dokumentation oder 404 */
function qs_vf_index(array $liste, $id, string $was): int
{
    $id = is_string($id) ? $id : '';
    foreach ($liste as $i => $e) if (($e['id'] ?? '') === $id && $id !== '') return $i;
    fail("$was nicht gefunden.", 404);
    return -1;
}
/* Steht das IT-System in einer freigegebenen Fassung? (dann nicht löschen, nur außer Betrieb setzen) */
function qs_vf_system_in_fassung(array $doku, string $id): bool
{
    foreach ($doku['fassungen'] as $f) foreach ($f['inhalt']['systeme'] ?? [] as $s) if (($s['id'] ?? '') === $id) return true;
    return false;
}

/* ---------- Prüfen der Eingaben ---------- */
function qs_vf_zeile($v, int $max, string $was): string
{
    $t = qs_text($v, $max, $was);
    if (strpos($t, "\n") !== false) throw new InvalidArgumentException("$was: bitte ohne Zeilenumbruch.");
    return $t;
}
function qs_vf_kopf_felder(array $b): array
{
    $k = ['titel' => qs_vf_zeile($b['titel'] ?? '', 200, 'Bezeichnung'), 'gesellschaft' => qs_vf_zeile($b['gesellschaft'] ?? '', 200, 'Unternehmen'),
          'verantwortlich' => qs_kuerzel($b['verantwortlich'] ?? '', 'Verantwortlich')];
    if ($k['titel'] === '') throw new InvalidArgumentException('Bitte eine Bezeichnung angeben.');
    return $k;
}
function qs_vf_abschnitt_felder(array $b, array $doku): array
{
    $bekannt = array_column($doku['systeme'], 'id');
    $roh = $b['systeme'] ?? [];
    if (!is_array($roh)) throw new InvalidArgumentException('IT-Systeme: ungültige Angaben.');
    $systeme = [];
    foreach ($roh as $x) {
        if (!is_string($x) || !in_array($x, $bekannt, true)) throw new InvalidArgumentException('IT-Systeme: unbekanntes System.');
        if (!in_array($x, $systeme, true)) $systeme[] = $x;
    }
    try { $verweise = qs_verweise($b['verweise'] ?? []); }
    catch (InvalidArgumentException $e) { throw new InvalidArgumentException(str_replace('Wo? Womit?', 'QM-Dokumente', $e->getMessage())); }
    $a = ['teil' => qs_wahl($b['teil'] ?? '', array_keys(QS_VF_TEILE), 'Teil'), 'titel' => qs_vf_zeile($b['titel'] ?? '', 200, 'Überschrift'),
          'text' => qs_text($b['text'] ?? '', 20000, 'Beschreibung'), 'systeme' => $systeme, 'verweise' => $verweise,
          'zustaendig' => qs_kuerzel($b['zustaendig'] ?? '', 'Zuständig'), 'fertig' => !empty($b['fertig'])];
    if ($a['titel'] === '') throw new InvalidArgumentException('Bitte eine Überschrift angeben.');
    if ($a['fertig'] && $a['text'] === '' && !$a['verweise']) throw new InvalidArgumentException('„Fertig“ braucht Inhalt: bitte einen Text schreiben oder ein QM-Dokument verknüpfen.');
    return $a;
}
function qs_vf_system_felder(array $b): array
{
    $s = ['name' => qs_vf_zeile($b['name'] ?? '', 120, 'Name'), 'art' => qs_wahl($b['art'] ?? 'vor', array_keys(QS_VF_SYSTEM_ART), 'Art'),
          'zweck' => qs_text($b['zweck'] ?? '', 2000, 'Zweck und Daten'), 'anbieter' => qs_vf_zeile($b['anbieter'] ?? '', 200, 'Anbieter / Version'),
          'betrieb' => qs_wahl($b['betrieb'] ?? 'lokal', array_keys(QS_VF_BETRIEB), 'Betrieb'), 'ort' => qs_vf_zeile($b['ort'] ?? '', 300, 'Speicherort'),
          'zustaendig' => qs_kuerzel($b['zustaendig'] ?? '', 'Zuständig'), 'sicherung' => qs_text($b['sicherung'] ?? '', 2000, 'Sicherung und Aufbewahrung'),
          'schnittstellen' => qs_text($b['schnittstellen'] ?? '', 2000, 'Schnittstellen'), 'seit' => qs_datum($b['seit'] ?? '', 'Im Einsatz seit', false),
          'bis' => qs_datum($b['bis'] ?? '', 'Außer Betrieb seit', false)];
    if ($s['name'] === '') throw new InvalidArgumentException('Bitte den Namen des Systems angeben.');
    if ($s['seit'] !== '' && $s['bis'] !== '' && $s['bis'] < $s['seit']) throw new InvalidArgumentException('„Außer Betrieb seit“ liegt vor „Im Einsatz seit“.');
    return $s;
}

/* ---------- Verknüpfte QM-Dokumente ---------- */
/* Verweis „2.5-A01 Rechnungsbearbeitung“ → Dokument, wenn die Dokumenten-Nr. vorne steht (wie verweisDok() in qs.js) */
function qs_vf_dok_finden(array $dokumente, string $verweis): ?array
{
    $t = mb_strtolower(preg_replace('/\s+/u', ' ', $verweis) ?? $verweis);
    $best = null; $laenge = 0;
    foreach ($dokumente as $d) {
        $nr = mb_strtolower((string)($d['nr'] ?? ''));
        if ($nr === '' || mb_strlen($nr) <= $laenge) continue;
        if ($t === $nr || strpos($t, $nr . ' ') === 0 || strpos($t, $nr . '_') === 0) { $best = $d; $laenge = mb_strlen($nr); }
    }
    return $best;
}
/* Stand eines verknüpften Dokuments: gültige Version mit Datum (leer, wenn keine gilt oder kein Dokument gefunden wurde) */
function qs_vf_dok_stand(?array $d): array
{
    if ($d === null) return ['dok' => '', 'nr' => '', 'titel' => '', 'version' => '', 'datum' => ''];
    $g = !empty($d['eingezogen']) ? null : qs_ver_index($d, ['freigegeben']);
    return ['dok' => (string)$d['id'], 'nr' => (string)($d['nr'] ?? ''), 'titel' => (string)($d['titel'] ?? ''),
            'version' => $g === null ? '' : (string)($d['versionen'][$g]['nr'] ?? ''), 'datum' => $g === null ? '' : (string)($d['versionen'][$g]['datum'] ?? '')];
}

/* ---------- Schnappschuss, Abweichung, Überprüfung ---------- */
/* Inhalt, wie er in eine Fassung eingeht: Kopf, Abschnitte mit Nummer und dem Stand der verknüpften QM-Dokumente,
   IT-Systeme, Liste der verknüpften QM-Dokumente, Namen zu den verwendeten Kürzeln */
function qs_vf_inhalt(array $doku, array $dokumente, array $stamm): array
{
    $abschnitte = $doku['abschnitte'];
    qs_vf_sortieren($abschnitte);
    $nr = qs_vf_nummern($abschnitte);
    $out = []; $doks = []; $kuerzel = [$doku['verantwortlich']];
    foreach ($abschnitte as $a) {
        if (!isset($nr[$a['id']])) continue;
        $verweise = [];
        foreach ($a['verweise'] as $v) {
            $st = qs_vf_dok_stand(qs_vf_dok_finden($dokumente, (string)$v));
            $verweise[] = ['text' => (string)$v] + $st;
            if ($st['dok'] !== '') $doks[$st['dok']] = $st;
        }
        $kuerzel[] = $a['zustaendig'];
        $out[] = ['id' => (string)$a['id'], 'teil' => $a['teil'], 'nr' => $nr[$a['id']], 'titel' => $a['titel'], 'text' => $a['text'],
                  'zustaendig' => $a['zustaendig'], 'systeme' => $a['systeme'], 'verweise' => $verweise];
    }
    $systeme = [];
    foreach ($doku['systeme'] as $s) { $x = ['id' => (string)$s['id']]; foreach (QS_VF_SYSTEM_INHALT as $f) $x[$f] = $s[$f]; $systeme[] = $x; $kuerzel[] = $s['zustaendig']; }
    $doks = array_values($doks);
    usort($doks, function ($a, $b) { return qs_nat_cmp($a['nr'], $b['nr']); });
    $personen = [];
    foreach ($stamm['personen'] as $p) if (in_array((string)($p['id'] ?? ''), $kuerzel, true) && (string)$p['id'] !== '')
        $personen[(string)$p['id']] = trim((string)($p['name'] ?? '') . ((string)($p['funktion'] ?? '') !== '' ? ', ' . $p['funktion'] : ''));
    ksort($personen);
    $kopf = [];
    foreach (QS_VF_KOPF as $f) $kopf[$f] = $doku[$f];
    return $kopf + ['abschnitte' => $out, 'systeme' => $systeme, 'dokumente' => $doks, 'personen' => $personen];
}
/* Was hat sich gegenüber einer Fassung geändert? „zeilen“ = Änderungshistorie in Worten, „abschnitte“ = neue und
   geänderte Abschnitte (Kennungen, für die Markierung in der Oberfläche), „dokumente“ = QM-Dokumente mit anderer Version */
function qs_vf_abweichung(array $neu, array $alt): array
{
    $kern = function (array $a): array { return [$a['teil'], $a['titel'], $a['text'], $a['zustaendig'], $a['systeme'], array_column($a['verweise'], 'text')]; };
    $name = function (array $a): string { return trim((string)($a['nr'] ?? '') . ' ' . (string)($a['titel'] ?? '')); };
    $nach = function (array $liste, string $schluessel): array { $o = []; foreach ($liste as $e) $o[(string)($e[$schluessel] ?? '')] = $e; return $o; };
    $altA = $nach($alt['abschnitte'] ?? [], 'id'); $neuA = $nach($neu['abschnitte'], 'id');
    $zeilen = []; $ids = []; $doks = [];
    $kopf = false;
    foreach (QS_VF_KOPF as $f) if ((string)($neu[$f] ?? '') !== (string)($alt[$f] ?? '')) $kopf = true;
    if ($kopf) $zeilen[] = 'Allgemeine Angaben geändert (Bezeichnung, Unternehmen oder Verantwortlicher)';
    foreach ($neuA as $id => $a) {
        if (!isset($altA[$id])) { $zeilen[] = 'Neu: ' . $name($a); $ids[] = (string)$id; }
        elseif ($kern($a) !== $kern($altA[$id])) { $zeilen[] = 'Geändert: ' . $name($a); $ids[] = (string)$id; }
    }
    foreach ($altA as $id => $a) if (!isset($neuA[$id])) $zeilen[] = 'Entfallen: ' . $name($a);
    if (array_values(array_intersect(array_keys($altA), array_keys($neuA))) !== array_values(array_intersect(array_keys($neuA), array_keys($altA))))
        $zeilen[] = 'Reihenfolge der Abschnitte geändert';
    $altS = $nach($alt['systeme'] ?? [], 'id'); $neuS = $nach($neu['systeme'], 'id');
    $gleich = function (array $a, array $b): bool { foreach (QS_VF_SYSTEM_INHALT as $f) if ((string)($a[$f] ?? '') !== (string)($b[$f] ?? '')) return false; return true; };
    foreach ($neuS as $id => $s) {
        if (!isset($altS[$id])) $zeilen[] = 'IT-System neu: ' . $s['name'];
        elseif ($gleich($s, $altS[$id]) === false) $zeilen[] = ($s['bis'] !== '' && (string)($altS[$id]['bis'] ?? '') === '' ? 'IT-System außer Betrieb: ' : 'IT-System geändert: ') . $s['name'];
    }
    foreach ($altS as $id => $s) if (!isset($neuS[$id])) $zeilen[] = 'IT-System entfernt: ' . (string)($s['name'] ?? '');
    $altD = $nach($alt['dokumente'] ?? [], 'dok');
    foreach ($neu['dokumente'] as $d) {
        $x = $altD[$d['dok']] ?? null;
        if ($x === null || (string)($x['version'] ?? '') === (string)$d['version']) continue;
        $doks[] = ['dok' => $d['dok'], 'nr' => $d['nr'], 'titel' => $d['titel'], 'alt' => (string)($x['version'] ?? ''), 'neu' => (string)$d['version']];
        $zeilen[] = 'QM-Dokument ' . trim($d['nr'] . ' ' . $d['titel']) . ': ' . ($d['version'] === '' ? 'keine gültige Version mehr (bisher Version ' . ($x['version'] ?? '') . ')'
            : 'jetzt Version ' . $d['version'] . (($x['version'] ?? '') !== '' ? ' (bisher Version ' . $x['version'] . ')' : ''));
    }
    return ['offen' => (bool)$zeilen, 'abschnitte' => $ids, 'dokumente' => $doks, 'zeilen' => $zeilen];
}
/* Überprüfung: seit (letzte Fassung oder „ohne Änderung überprüft“), fällig ab (+ 12 Monate). Ohne Fassung keine Frist. */
function qs_vf_ueberpruefung(array $doku, string $heute): ?array
{
    $f = $doku['fassungen'];
    if (!$f) return null;
    $seit = (string)($f[count($f) - 1]['datum'] ?? '');
    foreach ($doku['pruefungen'] as $p) { $d = (string)($p['datum'] ?? ''); if ($d > $seit) $seit = $d; }
    if ($seit === '') return ['seit' => '', 'faelligAb' => '', 'faellig' => true];
    $ab = qs_plus_monate($seit, QS_VF_UEBERPRUEFUNG_MONATE);
    return ['seit' => $seit, 'faelligAb' => $ab, 'faellig' => $ab <= $heute];
}
/* Letzter Tag, an dem die Fassung mit dem Index $i galt (Tag vor „gültig ab“ der nächsten); leer = gilt noch */
function qs_vf_gueltig_bis(array $fassungen, int $i): string
{
    $n = $fassungen[$i + 1] ?? null;
    return $n === null ? '' : qs_plus_tage((string)$n['gueltigAb'], -1);
}
/* Neue Fassung bilden (prüft alle Voraussetzungen, schreibt nicht) */
function qs_vf_fassung_bilden(array $doku, array $dokumente, array $stamm, array $me, string $grund, string $gueltigAb, string $heute): array
{
    if (count($doku['fassungen']) >= QS_VF_MAX_FASSUNGEN) fail('Zu viele Fassungen.', 422);
    $inhalt = qs_vf_inhalt($doku, $dokumente, $stamm);
    if (!$inhalt['abschnitte']) throw new InvalidArgumentException('Die Dokumentation hat noch keine Abschnitte.');
    $offen = [];
    $fertig = []; foreach ($doku['abschnitte'] as $a) $fertig[$a['id']] = $a['fertig'] && ($a['text'] !== '' || $a['verweise']);
    foreach ($inhalt['abschnitte'] as $a) if (empty($fertig[$a['id']])) $offen[] = $a['nr'] . ' ' . $a['titel'];
    if ($offen) throw new InvalidArgumentException('Noch nicht fertig (' . count($offen) . '): ' . implode(', ', array_slice($offen, 0, 4))
        . (count($offen) > 4 ? ' und ' . (count($offen) - 4) . ' weitere' : '') . '. Bitte fertigstellen oder Abschnitte entfernen, die nicht zutreffen.');
    $letzte = $doku['fassungen'] ? $doku['fassungen'][count($doku['fassungen']) - 1] : null;
    $aenderungen = ['Erstfassung'];
    if ($letzte !== null) {
        $ab = qs_vf_abweichung($inhalt, is_array($letzte['inhalt'] ?? null) ? $letzte['inhalt'] : []);
        if (!$ab['offen']) throw new InvalidArgumentException('Seit der Fassung ' . (int)$letzte['nr'] . ' hat sich nichts geändert. Zur Bestätigung „Ohne Änderung überprüft“ vermerken.');
        if ($gueltigAb < (string)($letzte['gueltigAb'] ?? '')) throw new InvalidArgumentException('„Gültig ab“ liegt vor der Fassung ' . (int)$letzte['nr'] . ' (gültig ab ' . qs_de((string)$letzte['gueltigAb']) . ').');
        $aenderungen = $ab['zeilen'];
    }
    $f = ['nr' => (int)($letzte['nr'] ?? 0) + 1, 'datum' => $heute, 'gueltigAb' => $gueltigAb, 'grund' => $grund, 'freigegeben' => qs_wer($me),
          'inhalt' => $inhalt, 'aenderungen' => $aenderungen];
    if (strlen((string)json_encode($f, JSON_UNESCAPED_UNICODE)) > QS_VF_MAX_FASSUNG_BYTES)
        fail('Die Dokumentation ist zu umfangreich für eine Fassung. Bitte lange Texte in QM-Dokumente auslagern und verknüpfen.', 422);
    return $f;
}

/* ---------- Antwort für die Oberfläche ---------- */
/* Dokumentation für die Oberfläche: Abschnitte sortiert mit Nummer, Fassungen ohne Inhalt (den liefert der Export als
   PDF), Abweichung seit der letzten Fassung, Überprüfung */
function qs_vf_aus(array $doku, array $dokumente, array $stamm, string $heute): array
{
    $doku = qs_vf_normal($doku);
    $abschnitte = $doku['abschnitte'];
    qs_vf_sortieren($abschnitte);
    $nr = qs_vf_nummern($abschnitte);
    foreach ($abschnitte as &$a) $a['nr'] = $nr[$a['id']] ?? '';
    unset($a);
    $f = $doku['fassungen'];
    $letzte = $f ? $f[count($f) - 1] : null;
    $out = $doku;
    $out['abschnitte'] = $abschnitte;
    $out['fassungen'] = [];
    foreach ($f as $i => $x) $out['fassungen'][] = ['nr' => (int)($x['nr'] ?? 0), 'datum' => (string)($x['datum'] ?? ''), 'gueltigAb' => (string)($x['gueltigAb'] ?? ''),
        'gueltigBis' => qs_vf_gueltig_bis($f, $i), 'grund' => (string)($x['grund'] ?? ''), 'von' => (string)($x['freigegeben']['von'] ?? ''),
        'aenderungen' => is_array($x['aenderungen'] ?? null) ? array_values($x['aenderungen']) : []];
    $out['seitFassung'] = $letzte === null ? null : qs_vf_abweichung(qs_vf_inhalt($doku, $dokumente, $stamm), is_array($letzte['inhalt'] ?? null) ? $letzte['inhalt'] : []);
    $out['ueberpruefung'] = qs_vf_ueberpruefung($doku, $heute);
    foreach ($out['systeme'] as &$s) $s['inFassung'] = qs_vf_system_in_fassung($doku, (string)$s['id']);
    unset($s);
    return $out;
}
/* Dokumentation für eine Änderung laden (unter der Sperre): [Speicher-Dokument, Index, Dokumentation] oder 404 */
function qs_vf_laden($id): array
{
    $doc = qs_doc(QS_VF_DOKUMENT);
    $i = qs_vf_index($doc['liste'], $id, 'Verfahrensdokumentation');
    return [$doc, $i, qs_vf_normal($doc['liste'][$i])];
}
function qs_vf_antworten(array $doku): void
{
    respond(['ok' => true, 'doku' => qs_vf_aus($doku, qs_doc('qs-dokumente')['liste'], qs_stamm(), qs_heute())]);
}
/* Dokumentation nach einer Änderung speichern: Stand hochzählen, „geändert“ setzen */
function qs_vf_ablegen(array &$doc, int $i, array $doku, array $me): array
{
    $doku['rev'] = (int)($doku['rev'] ?? 0) + 1;
    $doku['geaendert'] = qs_wer($me);
    $doc['liste'][$i] = $doku;
    qs_schreiben(QS_VF_DOKUMENT, $doc);
    return $doku;
}
