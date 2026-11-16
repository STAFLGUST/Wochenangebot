/* STAFL-Plattform · QM-System – Organigramm in einem gelenkten Dokument: Karte in der Seitenleiste des Dokuments (karte(x), aus
   renderDok in qs.js) und ein Fenster zum Ansehen bzw. Bearbeiten; Hilfen und Zustand über die Brücke window.STAFL_QS.
   Regeln, Rechte und die Übernahme der gültigen Struktur entscheidet allein der Server (GR-103). Der Baum (organigramm.css)
   ordnet nach derselben Regel an wie die PDF (qs_organigramm_lage in app/api/module/qs/organigramm.php). Kein Inline-Skript (CSP). */
'use strict';
(() => {
  const Q = window.STAFL_QS;
  if (!Q) return;
  const { $, S, esc, api, chip, datum, icon, darf, offene } = Q;
  const GRENZEN = { personen: 10, titel: 120, hinweis: 200 };   // wie QS_OG_MAX_* in app/api/module/qs/organigramm.php
  const G = { dok: '', version: '', edit: false, rev: 0, knoten: [], namen: null, wahl: '', geaendert: false, speichert: false, wieder: null, zoom: 1 };
  const dok = () => S.d.dokumente.find((x) => x.id === G.dok) || null;
  const person = (kz) => S.d.personen.find((p) => p.id === kz) || null;
  const name = (kz) => (G.namen ? G.namen[kz] || kz : (person(kz) || {}).name || `${kz} (nicht in den Personen)`);
  const knoten = (id) => G.knoten.find((k) => k.id === id) || null;
  const unter = (id, art) => G.knoten.filter((k) => k.ueber === id && (!art || k.art === art));
  const nachkommen = (id) => unter(id).flatMap((k) => [k.id, ...nachkommen(k.id)]);
  const kopie = (v) => ((v && v.organigramm) || { knoten: [] }).knoten.map((k) => ({ ...k, personen: [...k.personen] }));
  const neueId = () => { let id; do id = 'k' + Math.random().toString(36).slice(2, 10); while (knoten(id)); return id; };
  const meldung = (text, ok = false) => { $('#og-meldung').className = 'qm-meldung' + (ok ? ' ok' : ''); $('#og-meldung').textContent = text; };

  const ablage = () => `stafl-qs-organigramm:${S.d.ich.id}:${G.dok}:${G.version}`;
  /* Ungespeicherte Zeichnung je Person und Entwurf im Tab sichern: übersteht Ablauf der Anmeldung, Neuladen und das Schließen bei einem Konflikt.
     sessionStorage statt localStorage: auf gemeinsam genutzten Rechnern bleibt nach dem Schließen des Tabs nichts liegen. */
  function sichern() { try { sessionStorage.setItem(ablage(), JSON.stringify({ t: Date.now(), rev: G.rev, knoten: G.knoten })); } catch { /* privates Fenster oder voll */ } }
  function gesichert() {
    try { const s = JSON.parse(sessionStorage.getItem(ablage())); return s && Number.isInteger(s.rev) && Array.isArray(s.knoten) ? s : null; } catch { return null; }
  }
  function sicherungWeg() { try { sessionStorage.removeItem(ablage()); } catch { /* nicht verfügbar */ } }

  /* ---------- Karte in der Seitenleiste des Dokuments ---------- */
  function karte(x) {
    if (!S.d.gelenkt.includes(x.art)) return '';
    const g = Q.gueltige(x), o = offene(x), og = (v) => !!(v && v.organigramm);
    const entwurf = !!o && o.status === 'entwurf' && darf('bearbeiten'), sehen = og(o) && (darf('bearbeiten') || darf('freigeben'));
    const knopf = (art, text, primaer) => `<button class="btn${primaer ? ' primary' : ''}" type="button" data-og="${art}">${text}</button>`;
    if (!og(g) && !og(o)) {
      return entwurf ? `<section class="qm-karte og-karte"><h3>Organigramm</h3><p class="qm-hilfe">Stellen, Personen, Vertretungen und Beauftragte im QM-System zeichnen statt eine Datei abzulegen – die Freigabe legt die PDF-Fassung ab.</p>
        <div class="qm-knopfreihe">${knopf('bearbeiten', 'Organigramm im System zeichnen')}</div></section>` : '';
    }
    const stellen = (v) => `${v.organigramm.knoten.length} Stellen`;
    return `<section class="qm-karte og-karte"><h3>Organigramm${og(g) ? chip(`Version ${g.nr}: ${stellen(g)}`, 'gruen') : ''}${og(o) ? chip(`Entwurf: ${stellen(o)}`, 'gelb') : ''}</h3>
      <div class="qm-knopfreihe">${og(g) ? knopf('ansehen', `Version ${esc(g.nr)} ansehen`) : ''}${entwurf ? knopf('bearbeiten', 'Im Entwurf bearbeiten', true) : sehen ? knopf('entwurf', 'Entwurf ansehen') : ''}${
        sehen ? knopf('vorschau', `${icon('dokument')}PDF-Vorschau`) : ''}</div></section>`;
  }
  $('#qm-dk').addEventListener('click', async (ev) => {
    const b = ev.target.closest('[data-og]');
    if (!b) return;
    if (b.dataset.og !== 'vorschau') { oeffnen($('#qm-dk').dataset.dok, b.dataset.og); return; }
    const f = await vorschau($('#qm-dk').dataset.dok);
    if (f) Q.toast(f, true);
  });
  /* dieselbe PDF, die die Freigabe ablegt, mit „ENTWURF“ gekennzeichnet; liefert '' oder den Fehlertext */
  async function vorschau(id) {
    let res;
    try { res = await fetch(`../../api/?action=qs_organigramm_vorschau&dokument=${encodeURIComponent(id)}`, { credentials: 'same-origin', cache: 'no-store' }); } catch { return 'Keine Verbindung zum Server.'; }
    if (!res.ok) { let d = {}; try { d = await res.json(); } catch { /* keine JSON-Antwort */ } return d.error || `PDF-Vorschau fehlgeschlagen (${res.status}).`; }
    const m = /filename\*=UTF-8''([^;]+)/.exec(res.headers.get('Content-Disposition') || '');
    Q.speichereDatei(await res.blob(), m ? decodeURIComponent(m[1]) : 'Organigramm.pdf');
    return '';
  }

  /* ---------- Diagramm ---------- */
  function kastenHtml(k) {
    const pers = k.personen.length ? k.personen.map((p) => `<span>${esc(name(p))}</span>`).join('') : '<span class="og-unbesetzt">unbesetzt</span>';
    const inhalt = `<b>${esc(k.titel)}</b>${pers}${k.vertretung ? `<small>Vertretung: ${esc(name(k.vertretung))}</small>` : ''}${k.hinweis ? `<small>${esc(k.hinweis)}</small>` : ''}`;
    const klasse = `og-kasten${k.art === 'stab' ? ' og-stabkasten' : ''}${k.id === G.wahl ? ' gewaehlt' : ''}`;
    return G.edit ? `<button type="button" class="${klasse}" data-og-tat="waehlen" data-og-knoten="${esc(k.id)}">${inhalt}</button>` : `<div class="${klasse}">${inhalt}</div>`;
  }
  function knotenHtml(k) {
    const st = unter(k.id, 'stab'), li = unter(k.id, 'linie');
    let zeilen = '';
    for (let i = 0; i < st.length; i += 2) zeilen += `<div class="og-stabzeile"><div class="og-l">${kastenHtml(st[i])}</div><div class="og-r">${st[i + 1] ? kastenHtml(st[i + 1]) : ''}</div></div>`;
    const gestapelt = !st.length && li.length && li.every((c) => !unter(c.id).length);
    return `<div class="og-k">${kastenHtml(k)}${zeilen ? `<div class="og-stab${li.length ? '' : ' og-ende'}">${zeilen}</div>` : ''}${
      gestapelt ? `<div class="og-stapel">${li.map(kastenHtml).join('')}</div>` : li.length ? `<div class="og-kinder">${li.map(knotenHtml).join('')}</div>` : ''}</div>`;
  }
  function zeichnen() {
    $('#og-baum').innerHTML = G.knoten.length ? `<div class="og-wurzeln">${unter('').map(knotenHtml).join('')}</div>`
      : `<div class="og-leer"><p><b>Noch kein Organigramm – Stelle anlegen</b></p>${G.geaendert ? '<p class="qm-hilfe">Speichern ohne Stelle nimmt das Organigramm aus dem Entwurf.</p>' : ''}
        <label>Oberste Stelle<input class="qm-eingabe" id="og-erste" maxlength="${GRENZEN.titel}" value="Geschäftsführung"></label>
        <button class="btn primary" type="button" data-og-tat="erste">Stelle anlegen</button></div>`;
    $('#og-wieder').hidden = !G.wieder;
    $('#og-koerper').inert = G.speichert || !!G.wieder;   // gesperrt während des Speicherns und bis zur Antwort auf die Wiederherstellen-Frage
    if (!G.edit) return;
    const zeile = (k, t) => `<li><button type="button" class="og-zeile${k.id === G.wahl ? ' gewaehlt' : ''}" data-og-tat="waehlen" data-og-knoten="${esc(k.id)}" style="--t:${t}"><b>${esc(k.titel)}</b>${
      k.art === 'stab' ? '<em>Stab</em>' : ''}<span>${esc(k.personen.map(name).join(', ') || 'unbesetzt')}</span></button></li>` + [...unter(k.id, 'stab'), ...unter(k.id, 'linie')].map((c) => zeile(c, t + 1)).join('');
    $('#og-liste').innerHTML = unter('').map((k) => zeile(k, 0)).join('');
    $('#og-speichern').disabled = !G.geaendert || G.speichert;
  }
  function zoom(z) { G.zoom = Math.min(1.6, Math.max(0.3, Math.round(z * 100) / 100)); $('#og-baum').style.zoom = G.zoom; }
  function einpassen() { const b = $('#og-baum'); b.style.zoom = 1; zoom(Math.min(1, ($('#og-flaeche').clientWidth - 4) / Math.max(1, b.offsetWidth))); }

  /* ---------- Felder der gewählten Stelle ---------- */
  function felder() {
    const k = knoten(G.wahl);
    $('#og-felder').hidden = !k; $('#og-tipp').hidden = !!k;
    if (!k) return;
    const verboten = new Set([k.id, ...nachkommen(k.id)]);
    const waehlbar = S.d.personen.filter((p) => p.aktiv !== false || k.personen.includes(p.id) || k.vertretung === p.id);
    const opt = (wert, text, wahl) => `<option value="${esc(wert)}"${wert === wahl ? ' selected' : ''}>${esc(text)}</option>`;
    $('#og-titel-in').value = k.titel;
    $('#og-art').innerHTML = opt('linie', 'Linie (untergeordnet)', k.art) + (k.ueber && !unter(k.id).length ? opt('stab', 'Stabsstelle / Beauftragte', k.art) : '');
    $('#og-ueber').innerHTML = (k.art === 'linie' ? opt('', '— oberste Ebene —', k.ueber) : '')
      + G.knoten.filter((x) => x.art === 'linie' && !verboten.has(x.id)).map((x) => opt(x.id, x.titel, k.ueber)).join('');
    $('#og-pers').innerHTML = k.personen.map((p) => `<span class="qm-chip og-chip">${esc(name(p))}<button type="button" data-og-tat="person-weg" data-person="${esc(p)}" aria-label="${esc(name(p))} entfernen">×</button></span>`).join('')
      || '<span class="og-unbesetzt">unbesetzt</span>';
    $('#og-pers-neu').innerHTML = opt('', '+ Person hinzufügen …', '') + waehlbar.filter((p) => !k.personen.includes(p.id)).map((p) => opt(p.id, `${p.name} (${p.id})`, '')).join('');
    $('#og-pers-neu').disabled = k.personen.length >= GRENZEN.personen;
    $('#og-vertretung').innerHTML = opt('', '— keine —', k.vertretung) + waehlbar.map((p) => opt(p.id, `${p.name} (${p.id})`, k.vertretung)).join('')
      + (k.vertretung && !person(k.vertretung) ? opt(k.vertretung, name(k.vertretung), k.vertretung) : '');
    $('#og-hinweis').value = k.hinweis;
    const geschw = unter(k.ueber, k.art), i = geschw.indexOf(k);
    $('[data-og-tat="links"]').disabled = i <= 0;
    $('[data-og-tat="rechts"]').disabled = i >= geschw.length - 1;
    $('[data-og-tat="linie"]').disabled = $('[data-og-tat="stab"]').disabled = k.art === 'stab';
  }
  function waehle(id) {
    G.wahl = id; zeichnen(); felder();
    const b = $(`#og-baum [data-og-knoten="${CSS.escape(id)}"]`);
    if (b) b.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }
  function geaendert() { G.geaendert = true; sichern(); meldung(''); zeichnen(); }
  function neu(teil) {
    const k = { id: neueId(), personen: [], vertretung: '', hinweis: '', ...teil };
    G.knoten.push(k); geaendert(); waehle(k.id);
    $('#og-titel-in').focus(); $('#og-titel-in').select();
  }
  function tauschen(k, schritt) {
    const g = unter(k.ueber, k.art), n = g[g.indexOf(k) + schritt];
    if (!n) return;
    const a = G.knoten.indexOf(k), b = G.knoten.indexOf(n);
    [G.knoten[a], G.knoten[b]] = [G.knoten[b], G.knoten[a]];
    geaendert(); felder();
  }
  function loeschen(k) {
    const weg = new Set([k.id, ...nachkommen(k.id)]);
    if (weg.size > 1 && !confirm(`„${k.titel}“ mit ${weg.size - 1} untergeordneten Stellen löschen?`)) return;
    G.knoten = G.knoten.filter((x) => !weg.has(x.id)); G.wahl = '';
    geaendert(); felder();
  }
  /* Knöpfe (data-og-tat) und Felder (data-feld); k = gewählte Stelle – Knöpfe, die sie brauchen, sind ohne Wahl ausgeblendet */
  const TATEN = {
    schliessen, speichern, einpassen, loeschen,
    vorschau: async () => meldung(G.geaendert ? 'Die PDF-Vorschau zeigt den gespeicherten Stand – bitte zuerst speichern.' : await vorschau(G.dok)),
    kleiner: () => zoom(G.zoom - 0.1),
    groesser: () => zoom(G.zoom + 0.1),
    waehlen: (k, b) => waehle(b.dataset.ogKnoten),
    erste: () => neu({ titel: $('#og-erste').value.trim() || 'Geschäftsführung', ueber: '', art: 'linie' }),
    linie: (k) => neu({ titel: 'Neue Stelle', ueber: k.id, art: 'linie' }),
    stab: (k) => neu({ titel: 'Neue Stabsstelle', ueber: k.id, art: 'stab' }),
    links: (k) => tauschen(k, -1),
    rechts: (k) => tauschen(k, 1),
    'person-weg': (k, b) => { k.personen = k.personen.filter((p) => p !== b.dataset.person); geaendert(); felder(); },
    wiederherstellen: () => { Object.assign(G, { knoten: G.wieder.knoten, rev: G.wieder.rev, geaendert: true, wieder: null }); zeichnen(); felder(); einpassen(); },
    verwerfen: () => { sicherungWeg(); G.wieder = null; zeichnen(); },
  };
  const FELDER = {
    titel: (k, w) => { k.titel = w; },
    hinweis: (k, w) => { k.hinweis = w; },
    art: (k, w) => { k.art = w; },
    vertretung: (k, w) => { k.vertretung = w; },
    ueber: (k, w) => { k.ueber = w; G.knoten.push(G.knoten.splice(G.knoten.indexOf(k), 1)[0]); },   // unter der neuen Stelle ganz rechts
    person: (k, w) => { if (w) k.personen.push(w); },
  };

  /* ---------- Fenster ---------- */
  function fenster() {
    if ($('#dlg-og')) return $('#dlg-og');
    document.body.insertAdjacentHTML('beforeend', `<dialog class="qm-dialog og-dialog" id="dlg-og" aria-labelledby="og-titel"><div class="og-rahmen">
      <div class="qm-dialogkopf og-kopf"><div><span class="qm-sub" id="og-sub"></span><h2 id="og-titel">Organigramm</h2></div>
        <div class="og-werkzeug"><button class="btn sm" type="button" data-og-tat="kleiner" aria-label="Verkleinern" title="Verkleinern">−</button><button class="btn sm" type="button" data-og-tat="einpassen" title="Ganzes Organigramm zeigen">Einpassen</button><button class="btn sm" type="button" data-og-tat="groesser" aria-label="Vergrößern" title="Vergrößern">+</button>
          <button class="btn sm" type="button" id="og-vorschau" data-og-tat="vorschau">${icon('dokument')}PDF-Vorschau</button><a class="btn sm" id="og-pdf" download hidden>${icon('download')}PDF</a></div>
        <button class="qm-dialog-schliessen" type="button" id="og-zu" data-og-tat="schliessen" aria-label="Schließen">×</button></div>
      <div class="og-wieder" id="og-wieder" role="alert" hidden><span id="og-wieder-text"></span><div><button class="btn sm primary" type="button" data-og-tat="wiederherstellen">Wiederherstellen</button><button class="btn sm" type="button" data-og-tat="verwerfen">Verwerfen</button></div></div>
      <div class="og-koerper" id="og-koerper">
        <div class="og-flaeche" id="og-flaeche"><div class="og-baum" id="og-baum"></div></div>
        <aside class="og-seite" id="og-seite">
          <div class="qm-formraster og-felder" id="og-felder">
            <label class="qm-breit">Stelle / Funktion<input class="qm-eingabe" id="og-titel-in" data-feld="titel" maxlength="${GRENZEN.titel}"></label>
            <label>Art<select class="qm-eingabe" id="og-art" data-feld="art"></select></label>
            <label>Untergeordnet unter<select class="qm-eingabe" id="og-ueber" data-feld="ueber"></select></label>
            <div class="qm-breit og-personen">Person(en)<div class="og-chips" id="og-pers"></div><select class="qm-eingabe" id="og-pers-neu" data-feld="person" aria-label="Person hinzufügen"></select></div>
            <label class="qm-breit">Vertretung<select class="qm-eingabe" id="og-vertretung" data-feld="vertretung"></select></label>
            <label class="qm-breit">Hinweis<input class="qm-eingabe" id="og-hinweis" data-feld="hinweis" maxlength="${GRENZEN.hinweis}" placeholder="z. B. extern, bestellt seit …"></label>
            <div class="qm-breit og-taten"><button class="btn sm" type="button" data-og-tat="linie">+ Untergeordnete Stelle</button><button class="btn sm" type="button" data-og-tat="stab">+ Stabsstelle</button>
              <button class="btn sm" type="button" data-og-tat="links" aria-label="Nach links schieben" title="Nach links">←</button><button class="btn sm" type="button" data-og-tat="rechts" aria-label="Nach rechts schieben" title="Nach rechts">→</button>
              <button class="btn sm og-weg" type="button" data-og-tat="loeschen">Löschen</button></div>
          </div>
          <p class="qm-hilfe" id="og-tipp">Einen Kasten oder einen Eintrag der Gliederung wählen, um die Stelle zu bearbeiten.</p>
          <h3 class="qm-zwischen">Gliederung</h3>
          <ul class="og-liste" id="og-liste"></ul>
        </aside>
      </div>
      <p class="qm-meldung" id="og-meldung" role="alert"></p>
      <div class="qm-knopfreihe og-fuss" id="og-fuss"><button class="btn" type="button" data-og-tat="schliessen">Schließen</button><button class="btn primary" type="button" id="og-speichern" data-og-tat="speichern">Speichern</button></div>
    </div></dialog>`);
    const d = $('#dlg-og');
    // Esc selbst behandeln: Chrome schließt beim zweiten Esc ohne neue Nutzeraktion, ohne „cancel“ abzuwarten
    document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && d.open) { ev.preventDefault(); schliessen(); } });
    d.addEventListener('cancel', (ev) => { ev.preventDefault(); schliessen(); });
    d.addEventListener('click', (ev) => { const b = ev.target.closest('[data-og-tat]'); if (b) TATEN[b.dataset.ogTat](knoten(G.wahl), b); });
    const feld = (ev) => { const k = knoten(G.wahl), f = ev.target.dataset.feld; if (!k || !f) return false; FELDER[f](k, ev.target.value); geaendert(); return true; };
    $('#og-felder').addEventListener('input', (ev) => { if (ev.target.tagName === 'INPUT') feld(ev); });
    $('#og-felder').addEventListener('change', (ev) => { if (ev.target.tagName === 'SELECT' && feld(ev)) felder(); });
    return d;
  }
  /* art: 'ansehen' = gültige Version, 'entwurf' = offene Version nur lesen, 'bearbeiten' = offener Entwurf. Namen aus dem
     Schnappschuss der Version (ab dem Einreichen), im Entwurf die heutigen; rev = Stand beim Öffnen gegen fremde Änderungen,
     version = Entwurf, zu dem die Zeichnung gehört. Eine Sicherung dieses Entwurfs wird zuerst angeboten. */
  function oeffnen(id, art) {
    G.dok = id;
    const x = dok(), v = x && (art === 'ansehen' ? Q.gueltige(x) : offene(x));
    if (!v) return;
    Object.assign(G, { edit: art === 'bearbeiten', version: v.id, rev: x.rev, knoten: kopie(v), namen: (v.organigramm || {}).namen || null, wahl: '', geaendert: false, speichert: false });
    G.wieder = G.edit ? gesichert() : null;
    const d = fenster();
    if (G.wieder) $('#og-wieder-text').textContent = `Ungespeicherte Zeichnung vom ${Q.zeitpunkt(G.wieder.t)} wiederherstellen?`;
    d.classList.toggle('og-bearbeiten', G.edit);
    $('#og-titel').textContent = `${x.nr ? x.nr + ' ' : ''}${x.titel}`;
    $('#og-sub').textContent = art === 'ansehen' ? `Organigramm · Version ${v.nr} gültig seit ${datum(v.datum)}`
      : `Organigramm · Entwurf zu Version ${Q.naechsteVersion(x)}${G.edit ? '' : ' (nur ansehen)'}`;
    const pdf = art === 'ansehen' ? (v.dateien || []).find((f) => f.organigramm && !f.entfernt) : null;
    $('#og-pdf').hidden = !pdf;
    if (pdf) $('#og-pdf').href = `../../api/?action=qs_datei&id=${encodeURIComponent(pdf.id)}`;
    $('#og-vorschau').hidden = art === 'ansehen';
    $('#og-seite').hidden = !G.edit; $('#og-fuss').hidden = !G.edit;
    meldung('');
    if (!d.open) d.showModal();
    zeichnen(); felder(); einpassen();
  }
  function schliessen() {
    if (G.speichert) return;   // erst nach Antwort und Konfliktbehandlung, sonst fragte ein 409 bei geschlossenem Fenster nach
    if (G.geaendert) {
      if (!confirm('Ungespeicherte Änderungen am Organigramm verwerfen?')) return;
      sicherungWeg();
    }
    G.geaendert = false;
    $('#dlg-og').close();
  }
  /* Während der Anfrage samt Konfliktbehandlung ist die Zeichnung gesperrt: die Antwort überschreibt keine neuen Eingaben,
     Schließen und ein zweiter Lauf warten */
  function sperren(an) { G.speichert = an; zeichnen(); }
  async function speichern() {
    meldung('');
    sperren(true);
    const [text, ok] = await uebertragen();
    sperren(false);
    meldung(text, ok);
  }
  /* Zeichnung senden → [Meldung, gespeichert?]; nach einer Anmeldung in einem anderen Tab einmal mit neuem CSRF-Token erneut */
  async function uebertragen(tokenHolen = true) {
    const r = await api('qs_organigramm_save', { dokument: G.dok, version: G.version, rev: G.rev, organigramm: { knoten: G.knoten } });
    if (r.status === 403 && tokenHolen && (await Q.csrfNeu())) return uebertragen(false);
    if (r.status === 401) return ['Die Anmeldung ist abgelaufen. Bitte in einem neuen Tab anmelden und dann hier erneut speichern – die Zeichnung bleibt erhalten.'];
    if (r.status === 409 && r.data.code === 'konflikt') {
      if (!(await Q.neuLaden())) return ['Der neue Stand ließ sich nicht laden – bitte erneut speichern.'];
      const x = dok();
      if (!confirm(`Inzwischen geändert von ${(x.geaendert || {}).von || 'jemand anderem'} – Ihre Fassung trotzdem speichern?`)) return ['Nicht gespeichert. Ihre Fassung steht weiter hier; „Schließen“ verwirft sie.'];
      G.rev = x.rev;
      return uebertragen(tokenHolen);
    }
    if (r.status !== 200 || !r.data.ok) return [Q.fehlerText(r, 'Speichern fehlgeschlagen')];
    const d = r.data.dokument;
    S.d.dokumente[S.d.dokumente.findIndex((y) => y.id === d.id)] = d;
    Object.assign(G, { rev: d.rev, knoten: kopie(offene(d)), geaendert: false });
    sicherungWeg();
    felder();
    Q.oeffneDok(d.id);
    return ['Organigramm gespeichert.', true];
  }

  Q.organigramm = { karte };
})();
