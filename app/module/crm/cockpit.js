/* STAFL-Plattform · CRM · Cockpit (Auftrag des Inhabers 01.11.2026): „Mein Cockpit“ je Verkäufer, Master-Cockpit mit Umschalter
   und Vertreter-Auswahl (Recht crm.master) und der Reiter „Übersicht“ im Kunden-Pop-up (Signale, Umsatz und Menge mit Vorjahr,
   Monatsbalken, Top-Artikel, „Auffällig bei Artikeln“, nächster Schritt, letzte Aktivitäten, Ansprechpartner).
   Zahlen kommen nur über die Aktionen crm_cockpit und crm_kunde_umsatz; was der Mitarbeiter nicht sehen darf (Umsätze in €,
   Mengen in kg), liefert der Server gar nicht erst aus – fehlende Werte blendet die Seite aus. Wiedervorlagen, Anrufe, Chancen
   und Aktivitäten stammen aus den Daten von crm_start. Wird von crm.js aufgerufen (window.STAFL_CRM_COCKPIT). */
'use strict';
(() => {
  const NF0 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });
  const NF1 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const NF2 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const MONATE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  const MON_KURZ = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
  const WOCHENTAGE = ['', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
  const OFFEN = ['Interessent', 'Erstkontakt', 'Muster/Probe', 'Angebot', 'Verhandlung'];

  /* ---------- Zahlen (Umsatz in Cent, Menge in Tausendstel kg) ---------- */
  const da = (v) => v !== undefined && v !== null;
  const minus = (x, f) => (x < 0 ? '−' : '') + f(Math.abs(x));   // echtes Minuszeichen wie bei den Prozenten
  const euro = (c) => (!da(c) ? '—' : minus(c, (a) => (a >= 1e8 ? NF2.format(a / 1e8) + ' Mio. €' : NF0.format(Math.round(a / 100)) + ' €')));
  const kg = (m) => (!da(m) ? '—' : minus(m, (a) => (a >= 1e6 ? NF1.format(a / 1e6) + ' t' : NF0.format(Math.round(a / 1000)) + ' kg')));
  const preis = (c, m) => (!da(c) || !m ? '—' : NF2.format(c * 10 / m) + ' €/kg');
  const prozent = (x) => (!da(x) ? '' : (x > 0.0005 ? '+' : x < -0.0005 ? '−' : '±') + NF1.format(Math.abs(x) * 100) + ' %');
  const veraend = (j, v) => (!da(j) || !da(v) || v <= 0 ? null : (j - v) / v);
  const richtung = (x) => (!da(x) ? '' : x > 0.0005 ? 'plus' : x < -0.0005 ? 'minus' : '');
  const plural = (n, eins, viele) => `${NF0.format(n)} ${n === 1 ? eins : viele}`;
  const monatName = (m) => (m ? MONATE[+m.slice(5, 7) - 1] : '');
  const tagMonat = (d) => (d ? `${d.slice(8, 10)}.${d.slice(5, 7)}.` : '');

  const K = { d: null, wahl: null, laedt: 0, laeuft: false, fehler: '', host: null, c: null, ku: new Map() };

  /* ---------- Bereich der Ansicht (für Wiedervorlagen, Chancen, Aktivitäten aus crm_start) ---------- */
  function imBereich(k, d) {
    if (!d || d.ansicht === 'master' || d.ansicht === 'ohne') return true;
    if (d.ansicht === 'ohne_vertreter') return !k.vertreter && !k.vertreter2;
    return k.vertreter === d.vertreter || k.vertreter2 === d.vertreter;
  }
  /* Heute dran: fällige Wiedervorlagen (überfällige zuerst), Bestellpausen (Signal des Servers), Anrufe laut Rhythmus */
  function heuteDran(liste, d) {
    const c = K.c, l = [];
    for (const k of liste) {
      if (k.crm.naechsterSchritt && k.crm.wiedervorlage && c.tageBis(k.crm.wiedervorlage) <= 0) l.push({ art: 'wv', k, t: c.tageBis(k.crm.wiedervorlage) });
      else if (c.heuteAnrufen(k) && k.crm.anrufStatus !== 'Erledigt') l.push({ art: 'anruf', k });
    }
    for (const s of (d ? d.signale : [])) if (s.art === 'pause' && c.kunde(s.key)) l.push({ art: 'pause', k: c.kunde(s.key), s });
    const rang = { wv: 0, pause: 1, anruf: 2 };
    return l.sort((a, b) => rang[a.art] - rang[b.art] || (a.t ?? 0) - (b.t ?? 0) || a.k.firma.localeCompare(b.k.firma, 'de'));
  }

  /* ---------- Laden ---------- */
  async function laden(wahl) {
    const nr = ++K.laedt;
    K.laeuft = true;
    const r = await K.c.api('crm_cockpit', null, wahl ? '&vertreter=' + encodeURIComponent(wahl) : '');
    if (nr !== K.laedt) return;
    K.laeuft = false;
    if (r.status !== 200 || !r.data.ok) K.fehler = K.c.fehlerText(r, 'Das Cockpit konnte nicht geladen werden');
    else { K.fehler = ''; K.d = r.data; K.wahl = wahl; }
    if (K.host && !K.host.hidden) rendern();
  }
  function zeichne(host, c) {
    K.host = host; K.c = c;
    if (!K.d && !K.fehler) {
      if (!K.laeuft) laden(K.wahl);
      host.innerHTML = '<div class="crm-titel"><h1>Cockpit</h1><p>Wird geladen …</p></div>';
      return;
    }
    rendern();
  }

  /* ---------- Bausteine ---------- */
  function kachel(titel, wert, sub = '', x = null, cls = '') {
    const c = K.c;
    return `<div class="crm-wert crm-glas ${cls}"><span>${c.esc(titel)}</span><b title="${c.esc(wert)}">${c.esc(wert)}</b>${da(x) || sub
      ? `<small>${da(x) ? `<em class="crm-ck-d ${richtung(x)}">${c.esc(prozent(x))}</em> ` : ''}${c.esc(sub)}</small>` : ''}</div>`;
  }
  const pille = (art) => ({ wv: '<span class="crm-ck-art wv">Wiedervorlage</span>', anruf: '<span class="crm-ck-art anruf">Anruf</span>',
    pause: '<span class="crm-ck-art pause">Bestellpause</span>', weniger: '<span class="crm-ck-art weniger">Kauft weniger</span>',
    weg: '<span class="crm-ck-art weg">Artikel weg</span>', neu: '<span class="crm-ck-art neu">Neu</span>' })[art] || '';
  function pauseText(s) {
    return `seit ${plural(s.pause, 'Tag', 'Tagen')} nichts · sonst alle ${NF0.format(Math.round(s.abstand))} Tage${da(s.umsatzMonat) ? ` · üblich ${euro(s.umsatzMonat)} je Monat`
      : da(s.mengeMonat) ? ` · üblich ${kg(s.mengeMonat)} je Monat` : ''}`;
  }
  function wenigerText(s) {
    return `letzte 3 Monate ${prozent(s.anteil)} Menge ${s.basis === 'vorjahr' ? 'zum Vorjahr' : 'zu den 3 Monaten davor'}${s.vorAllem ? ` · vor allem ${s.vorAllem.name}` : ''}`;
  }
  function wegText(s) {
    const a = s.artikel[0];
    return `${a.name} seit ${plural(Math.round(a.pause / 7), 'Woche', 'Wochen')} nicht mehr${s.anzahl > 1 ? ` (+${s.anzahl - 1} weitere)` : ''}`;
  }
  function heuteZeile(h) {
    const c = K.c, k = h.k, tel = c.telefone(k)[0];
    let text = '', wann = '', cls = '';
    if (h.art === 'wv') { text = k.crm.naechsterSchritt; wann = h.t < 0 ? `überfällig ${plural(-h.t, 'Tag', 'Tage')}` : 'heute'; cls = h.t < 0 ? 'ueber' : ''; }
    if (h.art === 'anruf') { text = `Rhythmus: ${[k.crm.rhythmus1, k.crm.rhythmus2].filter(Boolean).join(' und ')}${k.crm.letzterKontakt ? ` · letzter Kontakt ${c.de(k.crm.letzterKontakt)}` : ''}`; wann = 'heute'; }
    if (h.art === 'pause') { text = pauseText(h.s); wann = `seit ${tagMonat(h.s.letzter)}`; cls = 'warn'; }
    return `<li class="h">${pille(h.art)}<div class="was">${c.firmaKnopf(k)}<small>${c.esc(text)}</small></div><span class="wann ${cls}">${c.esc(wann)}</span>
      ${tel ? `<a class="crm-rund klein crm-ck-tel" href="tel:${c.esc(tel.replace(/[^\d+]/g, ''))}" aria-label="${c.esc(k.firma)} anrufen">${c.icon('phone')}</a>` : '<span class="crm-ck-tel"></span>'}</li>`;
  }
  function signalZeile(s) {
    const c = K.c, k = c.kunde(s.key);
    if (!k) return '';
    let text = '', wert = '', cls = '';
    if (s.art === 'weniger') { text = wenigerText(s); wert = da(s.umsatz) ? euro(s.umsatz - s.umsatzBasis) : prozent(s.anteil); cls = 'minus'; }
    if (s.art === 'weg') { text = wegText(s); wert = `seit ${tagMonat(s.artikel[0].zuletzt)}`; }
    if (s.art === 'neu') { text = `erster Kauf ${c.de(s.erster)} · ${plural(s.kauftage, 'Lieferung', 'Lieferungen')}`; wert = da(s.umsatz) ? euro(s.umsatz) : da(s.menge) ? kg(s.menge) : 'neu'; cls = 'plus'; }
    if (s.art === 'pause') { text = pauseText(s); wert = `seit ${tagMonat(s.letzter)}`; cls = 'warn'; }
    const vt = K.d && K.d.ansicht === 'master' ? `<span class="crm-ck-vt">${c.esc(c.vName(s.vertreter) || 'ohne Vertreter')}</span>` : '';
    return `<li class="s${K.d && K.d.ansicht === 'master' ? ' mit-art' : ''}">${K.d && K.d.ansicht === 'master' ? pille(s.art) : ''}<div class="was">${c.firmaKnopf(k)}<small>${c.esc(text)}</small></div>${vt}<b class="wert ${cls}">${c.esc(wert)}</b></li>`;
  }
  /* Zwölf Monatsbalken (Umsatz, sonst Menge); der laufende Monat (bis zum Stand) heller */
  function balken(reihe) {
    const w = reihe.map((x) => (da(x.umsatz) ? x.umsatz : da(x.menge) ? x.menge : 0));
    const max = Math.max(1, ...w);
    return `<span class="crm-ck-balken" aria-hidden="true">${w.map((v, i) => `<i style="height:${Math.max(2, Math.round(Math.max(0, v) / max * 24))}px"${i === w.length - 1 ? ' class="lauf"' : ''}></i>`).join('')}</span>`;
  }
  function chancen(liste, titel) {
    const c = K.c, D = c.daten();
    const b = D.phasen.slice(0, 6).map((p) => [p, liste.filter((k) => k.crm.phase === p && k.aktiv).length]);
    const max = Math.max(1, ...b.map((x) => x[1]));
    return `<section class="crm-karte crm-glas"><h3>${c.esc(titel)}</h3>${b.map(([p, n]) => `<div class="crm-balken"><span>${c.esc(p)}</span><div class="spur"><i style="width:${n ? Math.max(3, n / max * 100) : 0}%"></i></div><b>${n}</b></div>`).join('')}</section>`;
  }
  function aktivitaeten(liste, titel) {
    const c = K.c, D = c.daten(), keys = new Set(liste.map((k) => k.key));
    const l = D.letzte.filter((a) => keys.has(a.key)).slice(0, 6);
    return `<section class="crm-karte crm-glas"><h3>${c.esc(titel)}</h3>${l.length ? `<ul class="crm-zeilen">${l.map((a) => `<li><div class="was">${c.kunde(a.key)
      ? `<button type="button" class="crm-firma" data-oeffnen="${c.esc(a.key)}">${c.esc(a.art)} · ${c.esc(c.kunde(a.key).firma)}</button>` : `<b>${c.esc(a.art)} · ${c.esc(a.firma)}</b>`}<small>${c.esc(c.deZeit(a.at))} · ${c.esc(a.von)}${a.notiz ? ' · ' + c.esc(a.notiz) : ''}</small></div></li>`).join('')}</ul>`
      : '<p class="crm-leer">Noch keine Aktivitäten.</p>'}</section>`;
  }

  /* ---------- Kopf mit Umschalter (Master) ---------- */
  function kopf(d, n) {
    const c = K.c, D = c.daten();
    const stand = d.stand ? `Umsatzdaten bis ${c.de(d.stand)}` : 'noch keine Umsatzdaten';
    let kicker = '', titel = 'Cockpit', sub = '';
    if (d.ansicht === 'master') { kicker = 'Master-Cockpit'; titel = 'Vertrieb gesamt'; sub = `${plural(D.vertreter.length, 'Vertreter', 'Vertreter')} · ${plural(d.kennzahlen.kunden, 'aktiver Kunde', 'aktive Kunden')} · ${stand}`; }
    else if (d.ansicht === 'ohne_vertreter') { kicker = 'Verkäufer-Ansicht'; titel = 'Kunden ohne Vertreter'; sub = `${plural(d.kennzahlen.kunden, 'aktiver Kunde', 'aktive Kunden')} · ${stand}`; }
    else if (d.ansicht === 'vertreter') {
      const eigen = d.vertreter === d.ich;
      kicker = `${eigen ? '' : 'Verkäufer-Ansicht · '}Vertreter ${d.vertreter}${c.vName(d.vertreter) !== d.vertreter ? ' · ' + c.vName(d.vertreter) : ''}`;
      titel = eigen ? 'Mein Cockpit' : `Cockpit · ${c.vName(d.vertreter)}`;
      sub = `${plural(d.kennzahlen.kunden, eigen ? 'eigener Kunde' : 'Kunde', eigen ? 'eigene Kunden' : 'Kunden')} · ${stand}`;
    } else sub = `${plural(n, 'Kunde', 'Kunden')} · Wiedervorlagen, Anrufe und Aktivitäten`;
    let wahl = '';
    if (d.rechte.master) {
      const master = d.ansicht === 'master';
      const wert = master ? '' : d.vertreter || '';
      wahl = `<div class="crm-ck-wahl"><div class="crm-seg" role="group" aria-label="Ansicht"><button type="button" data-ck-wahl="alle" aria-pressed="${master}">Master</button><button type="button" data-ck-modus="vertreter" aria-pressed="${!master}">Verkäufer-Ansicht</button></div>
        <label class="crm-ck-vtwahl"${master ? ' hidden' : ''}><span class="sr-only">Vertreter</span><select id="ck-vertreter">${D.vertreter.map((v) => `<option value="${c.esc(v.nr)}"${v.nr === wert ? ' selected' : ''}>${c.esc(v.nr)} – ${c.esc(v.name)}</option>`).join('')}<option value="_"${wert === '_' ? ' selected' : ''}>ohne Vertreter</option></select></label></div>`;
    } else if (d.ansicht === 'vertreter') wahl = '<div class="crm-ck-wahl"><button type="button" class="btn" data-ck-alle>Alle Kunden ansehen</button></div>';
    return `<div class="crm-titel crm-ck-titel"><div>${kicker ? `<span class="crm-ck-kicker">${c.esc(kicker)}</span>` : ''}<h1>${c.esc(titel)}</h1><p>${c.esc(sub)}</p></div>${wahl}</div>`;
  }

  /* ---------- Cockpit zeichnen ---------- */
  function rendern() {
    const c = K.c, D = c.daten(), d = K.d;
    if (!d) { K.host.innerHTML = `<div class="crm-titel"><h1>Cockpit</h1></div><p class="crm-fehler">${c.esc(K.fehler)}</p>`; return; }
    const bereich = D.kunden.filter((k) => imBereich(k, d));
    const heute = heuteDran(bereich, d);
    const z = d.kennzahlen, r = d.rechte, master = d.ansicht === 'master';
    const sig = d.signale.filter((s) => s.art !== 'pause');
    const anzahl = d.signaleGesamt || {};
    const sigGesamt = Object.values(anzahl).reduce((a, b) => a + b, 0);
    let html = kopf(d, bereich.length);
    if (K.fehler) html += `<p class="crm-fehler">${c.esc(K.fehler)}</p>`;
    if (d.ansicht === 'ohne') html += `<p class="crm-ck-hinweis crm-glas">Ihnen ist noch kein Vertreter zugeordnet – darum zeigt das Cockpit alle Kunden, aber keine Umsätze. Ein Administrator ordnet ihn unter Verwaltung → Mitarbeiter → „Vertreter im CRM“ zu.</p>`;
    else if (!d.stand) html += '<p class="crm-ck-hinweis crm-glas">Noch keine Umsatzdaten importiert – Umsätze, Mengen und Signale erscheinen nach dem Import der Kundenumsatztabelle (Verwaltung → Import).</p>';
    // Kennzahlen
    const k = [];
    const wv = heute.filter((h) => h.art === 'wv'), ueber = wv.filter((h) => h.t < 0).length;
    if (d.ansicht === 'ohne') k.push(kachel('Aktive Kunden', NF0.format(bereich.filter((x) => x.aktiv && x.art === 'kunde').length), `${bereich.filter((x) => x.art === 'interessent').length} Interessenten`));
    else k.push(kachel(master ? 'Aktive Kunden' : d.ansicht === 'vertreter' && d.vertreter === d.ich ? 'Meine Kunden' : 'Kunden', NF0.format(z.kunden),
      d.stand ? `${NF0.format(z.mitKauf)} mit Kauf in 12 Monaten${z.neu ? ` · ${z.neu} neu` : ''}` : 'aktiv'));
    if (z && d.stand) {   // Monat und Jahr bis zum Stand der Umsatzdaten, Vorjahr bis zum selben Tag
      if (da(z.monat.umsatz)) k.push(kachel(`Umsatz ${monatName(d.monat)}`, euro(z.monat.umsatz), 'zum Vorjahr', veraend(z.monat.umsatz, z.vjMonat.umsatz)));
      if (da(z.monat.menge)) k.push(kachel(`Menge ${monatName(d.monat)}`, kg(z.monat.menge), 'zum Vorjahr', veraend(z.monat.menge, z.vjMonat.menge)));
      if (!master && da(z.jahr.umsatz)) k.push(kachel(`Umsatz ${d.stand.slice(0, 4)}`, euro(z.jahr.umsatz), 'zum Vorjahr', veraend(z.jahr.umsatz, z.vjJahr.umsatz)));
    }
    const nPause = heute.filter((h) => h.art === 'pause').length, nAnruf = heute.filter((h) => h.art === 'anruf').length;
    const teile = [[wv.length, 'Wiedervorlage', 'Wiedervorlagen'], [nAnruf, 'Anruf', 'Anrufe'], [nPause, 'Bestellpause', 'Bestellpausen']].filter((x) => x[0]).map((x) => plural(...x));
    k.push(kachel('Heute dran', NF0.format(heute.length), master ? `${ueber} überfällig` : teile.join(' · ') || 'nichts fällig', null, ueber ? 'warn' : ''));
    if (master && d.stand) {
      const p = d.signale.filter((s) => s.art === 'pause'), w = d.signale.filter((s) => s.art === 'weniger');
      k.push(kachel('Bestellpausen', NF0.format(anzahl.pause || 0), r.euro && p.length ? `üblich ${euro(p.reduce((a, s) => a + s.umsatzMonat, 0))} je Monat` : 'Stammkunden'));
      k.push(kachel('Kauft weniger', NF0.format(anzahl.weniger || 0), r.euro && w.length ? `${euro(w.reduce((a, s) => a + s.umsatz - s.umsatzBasis, 0))} in 3 Monaten` : '3 Monate zum Vorjahr'));
    } else if (d.stand && d.ansicht !== 'ohne') {   // Bestellpausen zählen unter „Heute dran“
      const n = (anzahl.weniger || 0) + (anzahl.weg || 0) + (anzahl.neu || 0);
      const t = [[anzahl.weniger, 'kauft weniger'], [anzahl.weg, 'Artikel weg'], [anzahl.neu, 'neu']].filter((x) => x[0]).map((x) => `${x[0]} ${x[1]}`).join(' · ');
      k.push(kachel('Signale', NF0.format(n), t || 'alles im üblichen Rahmen'));
    }
    html += `<div class="crm-kpis crm-ck-kpis">${k.join('')}</div>`;

    if (master) html += vergleich(d);
    // Heute dran und Signale
    const heuteHtml = `<section class="crm-karte crm-glas"><div class="crm-karte-kopf"><h3>Heute dran <span class="crm-pille">${heute.length}</span></h3><button type="button" class="btn" data-gehe="wiedervorlagen">Alle Wiedervorlagen</button></div>
      <p class="crm-klein">Wiedervorlagen, Anrufe nach Rhythmus${d.stand ? ' und Bestellpausen' : ''}</p>
      ${heute.length ? `<ul class="crm-zeilen crm-ck-liste">${heute.slice(0, 10).map(heuteZeile).join('')}</ul>${heute.length > 10 ? `<p class="crm-klein">und ${heute.length - 10} weitere</p>` : ''}` : '<p class="crm-leer">Für heute steht nichts an.</p>'}</section>`;
    let rechts = '';
    if (master) {
      const auff = d.signale.filter((s) => s.art !== 'neu').slice();
      if (r.euro) auff.sort((a, b) => wertEuro(b) - wertEuro(a));
      rechts = `<section class="crm-karte crm-glas"><div class="crm-karte-kopf"><h3>Auffällige Kunden – alle Vertreter</h3></div><p class="crm-klein">Bestellpausen, kauft weniger, Artikel nicht mehr gekauft${r.euro ? ' · nach Umsatz' : ''}</p>
        ${auff.length ? `<ul class="crm-zeilen crm-ck-liste">${auff.slice(0, 10).map(signalZeile).join('')}</ul>` : '<p class="crm-leer">Keine Auffälligkeiten.</p>'}</section>`;
    } else if (d.ansicht !== 'ohne' && d.stand) {
      const gruppe = (art, titel) => { const l = sig.filter((s) => s.art === art); return l.length ? `<div class="crm-ck-gruppe"><h4>${titel}</h4><ul class="crm-zeilen crm-ck-liste">${l.slice(0, 6).map(signalZeile).join('')}</ul>${l.length > 6 ? `<p class="crm-klein">und ${l.length - 6} weitere</p>` : ''}</div>` : ''; };
      const inhalt = gruppe('weniger', 'Kauft weniger') + gruppe('weg', 'Artikel nicht mehr gekauft') + gruppe('neu', 'Neu dabei');
      rechts = `<section class="crm-karte crm-glas"><div class="crm-karte-kopf"><h3>Signale <span class="crm-pille">${sig.length}</span></h3></div><p class="crm-klein">aus den Umsatzdaten: letzte 3 Monate, Rhythmus je Artikel</p>${inhalt || '<p class="crm-leer">Keine Auffälligkeiten – alles im üblichen Rahmen.</p>'}</section>`;
    } else rechts = chancen(bereich, 'Verkaufschancen');
    html += `<div class="crm-ck-raster">${heuteHtml}${rechts}</div>`;
    // Top-Kunden, Chancen, Aktivitäten
    const unten = [];
    const chance = d.ansicht === 'ohne' || (!master && !d.stand) ? '' : chancen(bereich, master ? 'Verkaufschancen gesamt' : 'Meine Verkaufschancen');
    const akt = aktivitaeten(bereich, master || d.ansicht === 'ohne' ? 'Letzte Aktivitäten' : 'Meine letzten Aktivitäten');
    if (master) {   // Master: Chancen und Aktivitäten nebeneinander, Hinweise darunter
      const ohne = D.kunden.filter((x) => x.art === 'kunde' && x.aktiv && !x.vertreter && !x.vertreter2).length;
      const hinweis = (ohne ? `<p class="crm-ck-hinweis crm-glas">${plural(ohne, 'aktiver Kunde', 'aktive Kunden')} ohne Vertreter – bitte in der Verwaltung zuordnen.</p>` : '')
        + (z.ohneStammsatz ? `<p class="crm-klein">${plural(z.ohneStammsatz, 'Kunde', 'Kunden')} mit Umsatz, aber ohne Kundenstammsatz – in den Summen enthalten.</p>` : '');
      unten.push(`<div class="crm-ck-spalte">${chance}${hinweis}</div>`, akt);
    } else {
      if (d.top.length) unten.push(topKunden(d));
      unten.push(`<div class="crm-ck-spalte">${chance}${akt}</div>`);
    }
    html += `<div class="crm-ck-raster${unten.length === 1 ? ' eins' : ''}">${unten.join('')}</div>`;
    K.host.innerHTML = html;
  }
  /* Wirtschaftliches Gewicht eines Signals in Cent (Master: Sortierung „Auffällige Kunden“) */
  function wertEuro(s) {
    if (s.art === 'pause') return s.umsatzMonat || 0;
    if (s.art === 'weniger') return (s.umsatzBasis || 0) - (s.umsatz || 0);
    if (s.art === 'weg') return s.artikel.reduce((a, x) => a + (x.umsatz || 0), 0) / 12;
    return 0;
  }
  function topKunden(d) {
    const c = K.c, eu = d.rechte.euro, m = d.rechte.kg;
    const kopfZ = `<div class="crm-ck-zeile kopf" role="row"><span role="columnheader">Kunde</span>${eu ? '<span role="columnheader">Umsatz</span><span role="columnheader">± VJ</span>' : ''}${m ? `<span role="columnheader">Menge</span>${eu ? '' : '<span role="columnheader">± VJ</span>'}` : ''}<span role="columnheader">12 Monate</span><span role="columnheader">Letzter Kauf</span></div>`;
    const zeilen = d.top.map((t) => {
      const k = c.kunde(t.key); if (!k) return '';
      const x = eu ? veraend(t.j365.umsatz, t.v365.umsatz) : veraend(t.j365.menge, t.v365.menge);
      const d_ = `<span role="cell" class="crm-ck-d ${richtung(x)}" data-label="± VJ">${x === null ? (eu ? (t.v365.umsatz ? '' : 'neu') : (t.v365.menge ? '' : 'neu')) : c.esc(prozent(x))}</span>`;
      return `<div class="crm-ck-zeile" role="row"><span role="cell" class="kunde">${c.firmaKnopf(k)}<small>${c.esc([t.nr, t.ort].filter(Boolean).join(' · '))}</small></span>
        ${eu ? `<span role="cell" class="zahl" data-label="Umsatz">${euro(t.j365.umsatz)}</span>${d_}` : ''}${m ? `<span role="cell" class="zahl" data-label="Menge">${kg(t.j365.menge)}</span>${eu ? '' : d_}` : ''}
        <span role="cell" class="spark" data-label="12 Monate">${balken(t.reihe)}</span><span role="cell" class="zahl" data-label="Letzter Kauf">${c.de(t.zuletzt)}</span></div>`;
    }).join('');
    const zahlen = (eu ? 2 : 0) + (m ? (eu ? 1 : 2) : 0);
    const spalten = `minmax(0, 2.2fr) ${'minmax(0, 1fr) '.repeat(zahlen)}96px minmax(0, 1fr)`;
    return `<section class="crm-karte crm-glas crm-ck-top"><div class="crm-karte-kopf"><h3>${d.vertreter === d.ich ? 'Meine Top-Kunden' : 'Top-Kunden'}</h3></div><p class="crm-klein">letzte 12 Monate (365 Tage bis zum Stand) · Klick öffnet den Kunden</p>
      <div class="crm-ck-tabelle" role="table" aria-label="Top-Kunden" style="--ck-spalten: ${spalten}">${kopfZ}${zeilen}</div></section>`;
  }
  function vergleich(d) {
    const c = K.c, D = c.daten(), eu = d.rechte.euro, m = d.rechte.kg;
    // Heute dran und überfällig je Vertreter (Kunden mit zwei Vertretern zählen bei beiden)
    const je = {};
    const zu = (k) => { const v = [k.vertreter, k.vertreter2].filter(Boolean); return v.length ? [...new Set(v)] : ['_']; };
    for (const k of D.kunden) {
      const wvT = k.crm.naechsterSchritt && k.crm.wiedervorlage ? c.tageBis(k.crm.wiedervorlage) : Infinity;
      const dran = wvT <= 0 || (c.heuteAnrufen(k) && k.crm.anrufStatus !== 'Erledigt');
      for (const v of zu(k)) { je[v] = je[v] || { heute: 0, ueber: 0 }; if (dran) je[v].heute++; if (wvT < 0) je[v].ueber++; }
    }
    const zeilen = d.vergleich.map((v) => {
      const x = je[v.nr] || { heute: 0, ueber: 0 };
      const s = v.signale, nSig = s.weniger + s.weg + s.pause;
      const dx = eu ? veraend(v.monat.umsatz, v.vjMonat.umsatz) : m ? veraend(v.monat.menge, v.vjMonat.menge) : null;
      return `<tr><td class="name"><b>${c.esc(v.nr === '_' ? 'ohne Vertreter' : `${v.nr} – ${v.name}`)}</b></td><td class="zahl" data-label="Kunden">${v.kunden}</td>
        ${eu ? `<td class="zahl" data-label="Umsatz">${euro(v.monat.umsatz)}</td>` : ''}${eu || m ? `<td class="zahl crm-ck-d ${richtung(dx)}" data-label="± VJ">${c.esc(prozent(dx))}</td>` : ''}${m ? `<td class="zahl" data-label="Menge">${kg(v.monat.menge)}</td>` : ''}
        <td class="zahl" data-label="Heute dran">${x.heute + s.pause}</td><td class="zahl${x.ueber ? ' crm-ueber' : ''}" data-label="Überfällig">${x.ueber}</td><td class="zahl" data-label="Signale">${nSig ? `<span class="crm-pille warn" title="${s.pause} Pausen · ${s.weniger} weniger · ${s.weg} Artikel weg">${nSig}</span>` : '0'}</td>
        <td class="knopf"><button type="button" class="btn" data-ck-wahl="${c.esc(v.nr)}">Ansicht öffnen</button></td></tr>`;
    }).join('');
    return `<section class="crm-karte crm-glas crm-ck-vergleich"><div class="crm-karte-kopf"><h3>Vertreter im Vergleich</h3></div>
      <p class="crm-klein">${d.stand ? `${c.esc(monatName(d.monat))} ${d.monat.slice(0, 4)} bis ${tagMonat(d.stand)} zum Vorjahr · ` : ''}Kunden mit zwei Vertretern zählen bei beiden</p>
      <div class="crm-tabelle-rahmen"><table class="crm-tabelle crm-ck-karten"><thead><tr><th>Vertreter</th><th class="zahl">Kunden</th>${eu ? '<th class="zahl">Umsatz</th>' : ''}${eu || m ? '<th class="zahl">± VJ</th>' : ''}${m ? '<th class="zahl">Menge</th>' : ''}<th class="zahl">Heute dran</th><th class="zahl">Überfällig</th><th class="zahl">Signale</th><th></th></tr></thead>
      <tbody>${zeilen || '<tr><td colspan="9" class="crm-leer">Keine Vertreter in den Stammdaten.</td></tr>'}</tbody></table></div></section>`;
  }

  /* ---------- Bedienung ---------- */
  document.addEventListener('click', (e) => {
    const w = e.target.closest('[data-ck-wahl]');
    if (w && K.c) { laden(w.dataset.ckWahl); return; }
    if (e.target.closest('[data-ck-modus="vertreter"]') && K.d && K.d.ansicht === 'master') {
      const D = K.c.daten();
      laden(K.d.ich || (D.vertreter[0] && D.vertreter[0].nr) || '_');
      return;
    }
    if (e.target.closest('[data-ck-alle]') && K.c) { K.c.kundenAlle(); }
  });
  document.addEventListener('change', (e) => { if (e.target.id === 'ck-vertreter' && K.c) laden(e.target.value); });

  /* Erstes Signal eines Kunden aus dem geladenen Cockpit (Kundenliste: Kennzeichen und Auswahl „Mit Signal“) */
  function signale() {
    const m = new Map();
    for (const s of (K.d ? K.d.signale : [])) if (!m.has(s.key)) m.set(s.key, s);
    return m;
  }
  const signalKurz = (s) => (s.art === 'pause' ? 'Bestellpause' : s.art === 'weniger' ? `kauft weniger ${prozent(s.anteil)}` : s.art === 'weg' ? 'Artikel weg' : 'neu');

  /* ================= Kunden-Pop-up: Reiter „Übersicht“ ================= */
  async function uebersicht(host, key, c) {
    K.c = c;
    const alt = K.ku.get(key);
    if (alt) uebersichtZeichnen(host, key, alt);
    else host.innerHTML = '<p class="crm-leer">Umsätze werden geladen …</p>';
    const r = await c.api('crm_kunde_umsatz', null, '&key=' + encodeURIComponent(key));
    if (!host.isConnected || c.offen() !== key) return;
    if (r.status !== 200 || !r.data.ok) { host.innerHTML = `<p class="crm-fehler">${c.esc(c.fehlerText(r, 'Umsätze nicht geladen'))}</p>`; return; }
    K.ku.set(key, r.data);
    uebersichtZeichnen(host, key, r.data);
  }
  function uebersichtZeichnen(host, key, u) {
    const c = K.c, k = c.kunde(key), r = u.rechte, x = u.kunde;
    if (!k) return;
    const teile = [];
    if (!u.stand) teile.push('<p class="crm-ck-hinweis">Noch keine Umsatzdaten importiert.</p>');
    else if (!x) teile.push(`<p class="crm-ck-hinweis">Keine Umsätze für diesen Kunden in den Umsatzdaten (bis ${c.de(u.stand)}).</p>`);
    if (x) {
      // Hinweise: Bestellpause, kauft weniger, neu
      const hin = [];
      for (const s of x.signale) {
        if (s.art === 'pause') hin.push(`<div class="crm-ku-hinweis warn"><b>Bestellpause</b><span>Seit <b>${plural(s.pause, 'Tag', 'Tagen')}</b> nichts gekauft – sonst im Schnitt alle ${NF0.format(Math.round(s.abstand))} Tage${x.rhythmus.wochentage.length ? ` (meist ${x.rhythmus.wochentage.map((w) => WOCHENTAGE[w]).join(' und ')})` : ''}.</span></div>`);
        if (s.art === 'weniger') hin.push(`<div class="crm-ku-hinweis minus"><b>Kauft weniger</b><span>Letzte 3 Monate <b>${c.esc(prozent(s.anteil))} Menge</b> ${s.basis === 'vorjahr' ? 'zum Vorjahr' : 'zu den 3 Monaten davor'}${s.vorAllem ? `, vor allem ${c.esc(s.vorAllem.name)}` : ''}.</span></div>`);
        if (s.art === 'neu') hin.push(`<div class="crm-ku-hinweis plus"><b>Neu dabei</b><span>Erster Kauf am ${c.de(s.erster)} · ${plural(s.kauftage, 'Lieferung', 'Lieferungen')}.</span></div>`);
      }
      if (hin.length) teile.push(`<div class="crm-ku-hinweise">${hin.join('')}</div>`);
      // Kennzahlen
      const kz = [];
      if (da(x.w.j365.umsatz)) kz.push(kachel('Umsatz 12 Monate', euro(x.w.j365.umsatz), 'zum Vorjahr', veraend(x.w.j365.umsatz, x.w.v365.umsatz)));
      if (da(x.w.j365.menge)) kz.push(kachel('Menge 12 Monate', kg(x.w.j365.menge), 'zum Vorjahr', veraend(x.w.j365.menge, x.w.v365.menge)));
      if (da(x.w.j365.umsatz) && da(x.w.j365.menge)) kz.push(kachel('Ø Preis', preis(x.w.j365.umsatz, x.w.j365.menge), da(x.preisniveau) ? 'zum Ø aller Kunden' : '', da(x.preisniveau) ? x.preisniveau : null));
      const vor = x.zuletzt ? -c.tageBis(x.zuletzt) : null;
      kz.push(kachel('Letzter Kauf', x.zuletzt ? c.de(x.zuletzt) : '—', vor === null ? '' : vor === 0 ? 'heute' : `vor ${plural(vor, 'Tag', 'Tagen')}`, null, x.signale.some((s) => s.art === 'pause') ? 'warn' : ''));
      kz.push(kachel('Rhythmus', da(x.rhythmus.abstand) ? `alle ${NF0.format(Math.round(x.rhythmus.abstand))} Tage` : '—', `${plural(x.rhythmus.kauftage, 'Liefertag', 'Liefertage')} in 12 Monaten`));
      teile.push(`<div class="crm-kpis crm-ku-kpis">${kz.join('')}</div>`);
      // Monatsbalken (Umsatz, sonst Menge) mit Vorjahr
      const feld = r.euro ? 'umsatz' : r.kg ? 'menge' : null;
      if (feld) {
        const max = Math.max(1, ...x.monate.flatMap((mo) => [mo.jetzt[feld] || 0, mo.vj[feld] || 0]));
        teile.push(`<div class="crm-ku-monate"><div class="crm-ku-monate-kopf"><b>${feld === 'umsatz' ? 'Umsatz' : 'Menge'} je Monat</b><span class="crm-ku-legende"><i class="jetzt"></i>letzte 12 Monate<i class="vj"></i>Vorjahr</span></div>
          <div class="crm-ku-saeulen" role="img" aria-label="${feld === 'umsatz' ? 'Umsatz' : 'Menge'} je Monat mit Vorjahr">${x.monate.map((mo, i) => {
            const j = Math.max(0, mo.jetzt[feld] || 0), v = Math.max(0, mo.vj[feld] || 0), f = feld === 'umsatz' ? euro : kg;
            return `<div class="crm-ku-saeule" title="${c.esc(`${MON_KURZ[+mo.monat.slice(5, 7) - 1]} ${mo.monat.slice(0, 4)}: ${f(j)} · Vorjahr ${f(v)}`)}"><div class="spur"><i class="jetzt${i === x.monate.length - 1 ? ' lauf' : ''}" style="height:${Math.round(j / max * 100)}%"></i><i class="vj" style="height:${Math.round(v / max * 100)}%"></i></div><span>${MON_KURZ[+mo.monat.slice(5, 7) - 1]}</span></div>`;
          }).join('')}</div></div>`);
      }
      // Top-Artikel und Auffälliges
      teile.push(`<div class="crm-ku-raster"><section class="crm-ku-teil">${artikelTabelle(x, r)}</section><section class="crm-ku-teil">${auffaellig(x)}</section></div>`);
    }
    teile.push(`<div class="crm-ku-raster drei">${naechsterSchritt(k)}<section class="crm-ku-teil"><h3>Letzte Aktivitäten</h3><ul class="crm-zeilen" id="ku-akt"><li class="crm-leer">Wird geladen …</li></ul></section>${ansprechpartner(k)}</div>`);
    if (u.stand) teile.push(`<p class="crm-klein crm-ku-fuss">Umsatzdaten der Warenwirtschaft bis ${c.de(u.stand)}${r.euro || r.kg ? '' : ' · Umsätze und Mengen sind für Ihren Zugang ausgeblendet'}.</p>`);
    host.innerHTML = teile.join('');
    c.letzteAktivitaeten(key);
  }
  function artikelTabelle(x, r) {
    const c = K.c, eu = r.euro, m = r.kg;
    if (!x.artikel.length) return '<h3>Top-Artikel</h3><p class="crm-leer">Keine Artikel in den letzten 12 Monaten.</p>';
    const kopfZ = `<tr><th>Artikel</th>${m ? '<th class="zahl">Menge</th>' : ''}${eu ? '<th class="zahl">Umsatz</th>' : ''}${eu && m ? '<th class="zahl">Ø Preis</th>' : ''}${eu || m ? '<th class="zahl">± VJ</th>' : ''}<th class="zahl">Zuletzt</th></tr>`;
    const zeilen = x.artikel.map((a) => {
      const dx = eu ? veraend(a.j365.umsatz, a.v365.umsatz) : m ? veraend(a.j365.menge, a.v365.menge) : null;
      const neu = eu ? !a.v365.umsatz : m ? !a.v365.menge : false;
      const p = eu && m && a.j365.menge ? a.j365.umsatz * 10 / a.j365.menge : null;
      const abw = da(p) && a.preisAlle ? (p * 100 - a.preisAlle) / a.preisAlle : null;
      return `<tr><td class="name"><b>${c.esc(a.name)}</b><small>${c.esc([a.nr, a.fleischart].filter(Boolean).join(' · '))}</small></td>${m ? `<td class="zahl" data-label="Menge">${kg(a.j365.menge)}</td>` : ''}${eu ? `<td class="zahl" data-label="Umsatz">${euro(a.j365.umsatz)}</td>` : ''}
        ${eu && m ? `<td class="zahl" data-label="Ø Preis">${preis(a.j365.umsatz, a.j365.menge)}${da(abw) ? `<small class="crm-ck-d ${richtung(abw)}" title="zum Ø Preis aller Kunden">${c.esc(prozent(abw))} zum Ø</small>` : ''}</td>` : ''}
        ${eu || m ? `<td class="zahl crm-ck-d ${neu ? 'plus' : richtung(dx)}" data-label="± VJ">${neu ? 'neu' : c.esc(prozent(dx))}</td>` : ''}<td class="zahl" data-label="Zuletzt">${a.zuletzt ? c.esc(tagMonat(a.zuletzt)) : '—'}</td></tr>`;
    }).join('');
    return `<div class="crm-ku-teilkopf"><h3>Top-Artikel</h3><span class="crm-klein">letzte 12 Monate${x.artikelGesamt > x.artikel.length ? ` · ${x.artikel.length} von ${x.artikelGesamt}` : ''}</span></div>
      <div class="crm-tabelle-rahmen crm-ku-artikel"><table class="crm-tabelle crm-ck-karten"><thead>${kopfZ}</thead><tbody>${zeilen}</tbody></table></div>`;
  }
  function auffaellig(x) {
    const c = K.c, a = x.auffaellig;
    const gruppe = (titel, cls, l, text) => (l.length ? `<div class="crm-ku-auff ${cls}"><h4>${titel}</h4>${l.map((e) => `<div><b>${c.esc(e.name)}${e.anteil !== undefined ? ` ${c.esc(prozent(e.anteil))}` : ''}</b><small>${c.esc(text(e))}</small></div>`).join('')}</div>` : '');
    const html = gruppe('Nicht mehr gekauft', 'weg', a.weg, (e) => `zuletzt ${tagMonat(e.zuletzt)} · sonst alle ${NF0.format(Math.round(e.abstand))} Tage${da(e.menge) ? ` · 12 Monate ${kg(e.menge)}` : da(e.umsatz) ? ` · 12 Monate ${euro(e.umsatz)}` : ''}`)
      + gruppe('Kauft weniger', 'minus', a.weniger, (e) => `letzte 3 Monate${da(e.menge) ? ` ${kg(e.menge)} statt ${kg(e.mengeBasis)}` : da(e.umsatz) ? ` ${euro(e.umsatz)} statt ${euro(e.umsatzBasis)}` : ''} ${e.basis === 'vorjahr' ? 'zum Vorjahr' : 'zu den 3 Monaten davor'}`)
      + gruppe('Neu', 'plus', a.neu, (e) => `seit ${c.de(e.erster)} · ${plural(e.kauftage, 'Lieferung', 'Lieferungen')}${da(e.menge) ? ` · ${kg(e.menge)}` : ''}`);
    return `<div class="crm-ku-teilkopf"><h3>Auffällig bei Artikeln</h3></div>${html || '<p class="crm-leer">Nichts Auffälliges – die Artikel laufen wie üblich.</p>'}`;
  }
  function naechsterSchritt(k) {
    const c = K.c, b = c.darf(), s = k.crm.naechsterSchritt;
    const t = k.crm.wiedervorlage ? c.tageBis(k.crm.wiedervorlage) : null;
    const rh = [k.crm.rhythmus1, k.crm.rhythmus2].filter(Boolean).join(' und ');
    return `<section class="crm-ku-teil" id="ku-schritt"><h3>Nächster Schritt</h3>${s ? `<b class="crm-ku-schritt">${c.esc(s)}</b>` : '<p class="crm-leer">Kein nächster Schritt geplant.</p>'}
      <small class="crm-klein">${k.crm.wiedervorlage ? `<span class="${t < 0 ? 'crm-ueber' : ''}">Wiedervorlage ${c.de(k.crm.wiedervorlage)}</span>` : ''}${k.crm.wiedervorlage && rh ? ' · ' : ''}${rh ? 'Rhythmus: ' + c.esc(rh) : ''}</small>
      ${b && s ? `<div class="crm-knoepfe"><button type="button" class="btn" data-ku-erledigt>Erledigt</button><button type="button" class="btn" data-ku-verschieben>Verschieben</button></div>
        <div class="crm-ku-verschieben" hidden><label>Neue Wiedervorlage<input type="date" id="ku-wv" value="${c.esc(plusTage(k.crm.wiedervorlage && t > 0 ? k.crm.wiedervorlage : c.heute(), 7))}"></label><button type="button" class="btn primary" data-ku-wv-speichern>Übernehmen</button></div>` : ''}
      ${b ? `<button type="button" class="btn crm-ku-akt" data-ku-tab="verlauf" data-ku-fokus>${c.icon('plus')}Aktivität erfassen</button>` : ''}</section>`;
  }
  function plusTage(iso, n) { const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }
  function ansprechpartner(k) {
    const c = K.c;
    const leute = [...(k.ansprechpartner ? String(k.ansprechpartner).split(/[,;\n]+/).map((n) => ({ name: n.trim() })).filter((p) => p.name) : []), ...k.crm.kontakte];
    const tel = k.telefon ? `<div><b>Zentrale</b>${c.telLink(k.telefon)}</div>` : '';
    return `<section class="crm-ku-teil"><h3>Ansprechpartner</h3>${tel}${leute.slice(0, 5).map((p) => `<div><b>${c.esc(p.name || '—')}${p.funktion ? ' · ' + c.esc(p.funktion) : ''}</b>${p.telefon ? c.telLink(p.telefon) : p.email ? `<a href="mailto:${c.esc(p.email)}">${c.esc(p.email)}</a>` : ''}</div>`).join('')}
      ${!tel && !leute.length ? '<p class="crm-leer">Keine Ansprechpartner hinterlegt.</p>' : ''}${k.crm.praeferenz ? `<small class="crm-klein">${c.esc(k.crm.praeferenz)}</small>` : ''}</section>`;
  }

  window.STAFL_CRM_COCKPIT = {
    zeichne, uebersicht, signale, signalKurz,
    neu() { K.d = null; K.fehler = ''; K.ku.clear(); },
    vergessen(key) { K.ku.delete(key); },
    ansicht: () => K.d,
  };
})();
