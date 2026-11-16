/* STAFL-Plattform · Qualitätssicherung – Organigramm in einem gelenkten Dokument (Entscheidung des Inhabers 16.11.2026 „Im
   QM-System zeichnen“). Hilfen und Zustand über die Brücke window.STAFL_QS aus qs.js; die Struktur steht im Feld „organigramm“
   der Versionen (aus qs_start), gespeichert wird nur der offene Entwurf (qs_organigramm_save).
   karte(x) liefert die Karte für die Seitenleiste des Dokuments (aufgerufen aus renderDok in qs.js): gültige Version ansehen,
   Entwurf bearbeiten bzw. ansehen, im Entwurf „Organigramm im System zeichnen“. Ein Fenster für Ansicht und Bearbeitung:
   Diagramm als Baum (Linien aus organigramm.css, Stabsstellen seitlich an der Linie), Kasten wählen und in der Seitenleiste
   ändern, Gliederung als Einrückungsbaum (auf dem Handy der Weg zum Bearbeiten), Zoom, Drucken über #print-root, PDF-Fassung
   der gültigen Version. Ansehen zeigt die Namen aus dem Schnappschuss der Freigabe, der Entwurf die heutigen Personen.
   Rechte und Regeln (Zyklen, Grenzen, nur im Entwurf) prüft der Server (GR-103); hier nur, was angeboten wird. Kein Inline-Skript (CSP). */
'use strict';
(() => {
  const Q = window.STAFL_QS;
  if (!Q) return;
  const { $, S, esc, api, chip, datum, icon } = Q;
  const G = { dok: '', edit: false, knoten: [], namen: null, wahl: '', geaendert: false, zoom: 1 };
  const darf = (r) => !!(S.d && S.d.rechte && S.d.rechte[r]);
  const offene = (x) => (x.versionen || []).find((v) => ['entwurf', 'pruefung', 'geprueft'].includes(v.status)) || null;
  const naechste = (x) => (x.versionen || []).reduce((n, v) => Math.max(n, Number(v.nr) || 0), 0) + 1;
  const dok = () => S.d.dokumente.find((x) => x.id === G.dok) || null;
  const person = (kz) => S.d.personen.find((p) => p.id === kz) || null;
  const name = (kz) => (G.namen ? G.namen[kz] || kz : (person(kz) || {}).name || `${kz} (nicht in den Personen)`);
  const knoten = (id) => G.knoten.find((k) => k.id === id) || null;
  const unter = (id, art) => G.knoten.filter((k) => k.ueber === id && (!art || k.art === art));
  const nachkommen = (id) => unter(id).flatMap((k) => [k.id, ...nachkommen(k.id)]);
  const kopie = (liste) => liste.map((k) => ({ ...k, personen: [...k.personen] }));
  function neueId() { let id; do id = 'k' + Math.random().toString(36).slice(2, 10); while (knoten(id)); return id; }

  /* ---------- Karte in der Seitenleiste des Dokuments ---------- */
  function karte(x) {
    if (!S.d.gelenkt.includes(x.art)) return '';
    const g = Q.gueltige(x), o = offene(x), entwurf = !!o && o.status === 'entwurf' && darf('bearbeiten');
    const og = (v) => !!(v && v.organigramm);
    if (!og(g) && !og(o)) {
      return entwurf ? `<section class="qm-karte og-karte"><h3>Organigramm</h3><p class="qm-hilfe">Stellen, Personen, Vertretungen und Beauftragte im QM-System zeichnen statt eine Datei abzulegen – die Freigabe legt die PDF-Fassung ab.</p>
        <div class="qm-knopfreihe"><button class="btn" type="button" data-og="bearbeiten">Organigramm im System zeichnen</button></div></section>` : '';
    }
    const stellen = (v) => `${v.organigramm.knoten.length} Stellen`;
    return `<section class="qm-karte og-karte"><h3>Organigramm${og(g) ? chip(`Version ${g.nr}: ${stellen(g)}`, 'gruen') : ''}${og(o) ? chip(`Entwurf: ${stellen(o)}`, 'gelb') : ''}</h3>
      <div class="qm-knopfreihe">${og(g) ? `<button class="btn" type="button" data-og="ansehen">Version ${esc(g.nr)} ansehen</button>` : ''}${entwurf
        ? '<button class="btn primary" type="button" data-og="bearbeiten">Im Entwurf bearbeiten</button>'
        : og(o) && (darf('bearbeiten') || darf('freigeben')) ? '<button class="btn" type="button" data-og="entwurf">Entwurf ansehen</button>' : ''}</div></section>`;
  }
  $('#qm-dk').addEventListener('click', (ev) => { const b = ev.target.closest('[data-og]'); if (b) oeffnen($('#qm-dk').dataset.dok, b.dataset.og); });

  /* ---------- Diagramm ---------- */
  function kastenHtml(k) {
    const tag = G.edit ? 'button' : 'div';
    const pers = k.personen.length ? k.personen.map((p) => `<span>${esc(name(p))}</span>`).join('') : '<span class="og-unbesetzt">unbesetzt</span>';
    return `<${tag}${G.edit ? ' type="button"' : ''} class="og-kasten${k.art === 'stab' ? ' og-stabkasten' : ''}${k.id === G.wahl ? ' gewaehlt' : ''}" data-og-knoten="${esc(k.id)}"><b>${esc(k.titel)}</b>${pers}${
      k.vertretung ? `<small>Vertretung: ${esc(name(k.vertretung))}</small>` : ''}${k.hinweis ? `<small>${esc(k.hinweis)}</small>` : ''}</${tag}>`;
  }
  function knotenHtml(k) {
    const st = unter(k.id, 'stab'), li = unter(k.id, 'linie');
    let zeilen = '';
    for (let i = 0; i < st.length; i += 2) zeilen += `<div class="og-stabzeile"><div class="og-l">${kastenHtml(st[i])}</div><div class="og-r">${st[i + 1] ? kastenHtml(st[i + 1]) : ''}</div></div>`;
    return `<div class="og-k">${kastenHtml(k)}${zeilen ? `<div class="og-stab${li.length ? '' : ' og-ende'}">${zeilen}</div>` : ''}${li.length ? `<div class="og-kinder">${li.map(knotenHtml).join('')}</div>` : ''}</div>`;
  }
  const baumHtml = () => `<div class="og-wurzeln">${unter('').map(knotenHtml).join('')}</div>`;
  function zeichnen() {
    $('#og-baum').innerHTML = G.knoten.length ? baumHtml()
      : `<div class="og-leer"><p><b>Noch kein Organigramm – Stelle anlegen</b></p><label>Oberste Stelle<input class="qm-eingabe" id="og-erste" maxlength="120" value="Geschäftsführung"></label>
        <button class="btn primary" type="button" data-og-tat="erste">Stelle anlegen</button></div>`;
    if (!G.edit) return;
    const zeile = (k, t) => `<li><button type="button" class="og-zeile${k.id === G.wahl ? ' gewaehlt' : ''}" data-og-knoten="${esc(k.id)}" style="--t:${t}"><b>${esc(k.titel)}</b>${k.art === 'stab' ? '<em>Stab</em>' : ''}<span>${
      esc(k.personen.map(name).join(', ') || 'unbesetzt')}</span></button></li>` + [...unter(k.id, 'stab'), ...unter(k.id, 'linie')].map((c) => zeile(c, t + 1)).join('');
    $('#og-liste').innerHTML = unter('').map((k) => zeile(k, 0)).join('');
    $('#og-speichern').disabled = !G.geaendert;
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
    $('#og-pers').innerHTML = k.personen.map((p) => `<span class="qm-chip og-chip">${esc(name(p))}<button type="button" data-og-weg="${esc(p)}" aria-label="${esc(name(p))} entfernen">×</button></span>`).join('')
      || '<span class="og-unbesetzt">unbesetzt</span>';
    $('#og-pers-neu').innerHTML = opt('', '+ Person hinzufügen …', '') + waehlbar.filter((p) => !k.personen.includes(p.id)).map((p) => opt(p.id, `${p.name} (${p.id})`, '')).join('');
    $('#og-pers-neu').disabled = k.personen.length >= 10;
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
  function geaendert() { G.geaendert = true; $('#og-meldung').textContent = ''; zeichnen(); }
  function neu(teil) {
    const k = { id: neueId(), personen: [], vertretung: '', hinweis: '', ...teil };
    G.knoten.push(k); G.geaendert = true; waehle(k.id);
    $('#og-titel-in').focus(); $('#og-titel-in').select();
  }
  function tat(t) {
    if (t === 'erste') { neu({ titel: $('#og-erste').value.trim() || 'Geschäftsführung', ueber: '', art: 'linie' }); return; }
    const k = knoten(G.wahl);
    if (!k) return;
    if (t === 'linie' || t === 'stab') { neu({ titel: t === 'stab' ? 'Neue Stabsstelle' : 'Neue Stelle', ueber: k.id, art: t }); return; }
    if (t === 'links' || t === 'rechts') {
      const g = unter(k.ueber, k.art), n = g[g.indexOf(k) + (t === 'links' ? -1 : 1)];
      if (!n) return;
      const a = G.knoten.indexOf(k), b = G.knoten.indexOf(n);
      [G.knoten[a], G.knoten[b]] = [G.knoten[b], G.knoten[a]];
    } else if (t === 'loeschen') {
      const weg = new Set([k.id, ...nachkommen(k.id)]);
      if (weg.size > 1 && !confirm(`„${k.titel}“ mit ${weg.size - 1} untergeordneten Stellen löschen?`)) return;
      G.knoten = G.knoten.filter((x) => !weg.has(x.id)); G.wahl = '';
    }
    geaendert(); felder();
  }

  /* ---------- Fenster ---------- */
  function fenster() {
    if ($('#dlg-og')) return $('#dlg-og');
    document.body.insertAdjacentHTML('beforeend', `<dialog class="qm-dialog og-dialog" id="dlg-og" aria-labelledby="og-titel"><div class="og-rahmen">
      <div class="qm-dialogkopf og-kopf"><div><span class="qm-sub" id="og-sub"></span><h2 id="og-titel">Organigramm</h2></div>
        <div class="og-werkzeug"><button class="btn sm" type="button" data-og-zoom="-0.1" aria-label="Verkleinern" title="Verkleinern">−</button><button class="btn sm" type="button" data-og-zoom="0" title="Ganzes Organigramm zeigen">Einpassen</button><button class="btn sm" type="button" data-og-zoom="0.1" aria-label="Vergrößern" title="Vergrößern">+</button>
          <button class="btn sm" type="button" id="og-druck">${icon('druck')}Drucken</button><a class="btn sm" id="og-pdf" download hidden>${icon('download')}PDF</a></div>
        <button class="qm-dialog-schliessen" type="button" id="og-zu" aria-label="Schließen">×</button></div>
      <div class="og-koerper">
        <div class="og-flaeche" id="og-flaeche"><div class="og-baum" id="og-baum"></div></div>
        <aside class="og-seite" id="og-seite">
          <div class="qm-formraster og-felder" id="og-felder">
            <label class="qm-breit">Stelle / Funktion<input class="qm-eingabe" id="og-titel-in" maxlength="120"></label>
            <label>Art<select class="qm-eingabe" id="og-art"></select></label>
            <label>Untergeordnet unter<select class="qm-eingabe" id="og-ueber"></select></label>
            <div class="qm-breit og-personen">Person(en)<div class="og-chips" id="og-pers"></div><select class="qm-eingabe" id="og-pers-neu" aria-label="Person hinzufügen"></select></div>
            <label class="qm-breit">Vertretung<select class="qm-eingabe" id="og-vertretung"></select></label>
            <label class="qm-breit">Hinweis<input class="qm-eingabe" id="og-hinweis" maxlength="200" placeholder="z. B. extern, bestellt seit …"></label>
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
      <div class="qm-knopfreihe og-fuss" id="og-fuss"><button class="btn" type="button" id="og-abbrechen">Schließen</button><button class="btn primary" type="button" id="og-speichern">Speichern</button></div>
    </div></dialog>`);
    const d = $('#dlg-og');
    d.addEventListener('cancel', (ev) => { ev.preventDefault(); schliessen(); });
    d.addEventListener('click', (ev) => {
      const t = ev.target;
      if (t.closest('#og-zu, #og-abbrechen')) schliessen();
      else if (t.closest('#og-speichern')) speichern();
      else if (t.closest('#og-druck')) drucken();
      else if (t.closest('[data-og-zoom]')) { const z = Number(t.closest('[data-og-zoom]').dataset.ogZoom); if (z) zoom(G.zoom + z); else einpassen(); }
      else if (t.closest('[data-og-tat]')) tat(t.closest('[data-og-tat]').dataset.ogTat);
      else if (t.closest('[data-og-weg]')) { const k = knoten(G.wahl); k.personen = k.personen.filter((p) => p !== t.closest('[data-og-weg]').dataset.ogWeg); geaendert(); felder(); }
      else if (G.edit && t.closest('[data-og-knoten]')) waehle(t.closest('[data-og-knoten]').dataset.ogKnoten);
    });
    $('#og-felder').addEventListener('input', (ev) => {
      const k = knoten(G.wahl), f = { 'og-titel-in': 'titel', 'og-hinweis': 'hinweis' }[ev.target.id];
      if (!k || !f) return;
      k[f] = ev.target.value; geaendert();
    });
    $('#og-felder').addEventListener('change', (ev) => {
      const k = knoten(G.wahl), w = ev.target.value;
      if (!k) return;
      if (ev.target.id === 'og-art') k.art = w;
      else if (ev.target.id === 'og-ueber') { k.ueber = w; G.knoten.push(G.knoten.splice(G.knoten.indexOf(k), 1)[0]); }   // unter der neuen Stelle ganz rechts
      else if (ev.target.id === 'og-vertretung') k.vertretung = w;
      else if (ev.target.id === 'og-pers-neu' && w) k.personen.push(w);
      else return;
      geaendert(); felder();
    });
    return d;
  }
  /* art: 'ansehen' = gültige Version, 'entwurf' = offene Version nur lesen, 'bearbeiten' = offener Entwurf (ohne eigene
     Struktur beginnt er mit der gültigen Version, sonst leer) */
  function oeffnen(id, art) {
    G.dok = id;
    const x = dok();
    if (!x) return;
    const g = Q.gueltige(x), o = offene(x), v = art === 'ansehen' ? g : o;
    if (!v) return;
    const quelle = v.organigramm || (art === 'bearbeiten' && g && g.organigramm) || { knoten: [] };
    G.edit = art === 'bearbeiten';
    G.knoten = kopie(quelle.knoten);
    G.namen = art === 'ansehen' ? quelle.namen || {} : null;
    G.wahl = '';
    G.geaendert = G.edit && !v.organigramm && G.knoten.length > 0;
    const d = fenster();
    d.classList.toggle('og-bearbeiten', G.edit);
    $('#og-titel').textContent = `${x.nr ? x.nr + ' ' : ''}${x.titel}`;
    $('#og-sub').textContent = art === 'ansehen' ? `Organigramm · Version ${v.nr} gültig seit ${datum(v.datum)}`
      : `Organigramm · Entwurf zu Version ${naechste(x)}${G.edit ? '' : ' (nur ansehen)'}`;
    const pdf = art === 'ansehen' ? (v.dateien || []).find((f) => f.organigramm && !f.entfernt) : null;
    $('#og-pdf').hidden = !pdf;
    if (pdf) $('#og-pdf').href = `../../api/?action=qs_datei&id=${encodeURIComponent(pdf.id)}`;
    $('#og-seite').hidden = !G.edit; $('#og-fuss').hidden = !G.edit;
    $('#og-meldung').className = 'qm-meldung'; $('#og-meldung').textContent = '';
    if (!d.open) d.showModal();
    zeichnen(); felder(); einpassen();
  }
  function schliessen() {
    if (G.geaendert && !confirm('Ungespeicherte Änderungen am Organigramm verwerfen?')) return;
    G.geaendert = false;
    $('#dlg-og').close();
  }
  async function speichern() {
    const x = dok(), m = $('#og-meldung');
    m.className = 'qm-meldung'; m.textContent = ''; $('#og-speichern').disabled = true;
    const r = await api('qs_organigramm_save', { dokument: x.id, rev: x.rev, organigramm: { knoten: G.knoten } });
    if (r.status === 401) { G.geaendert = false; Q.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { m.textContent = Q.fehlerText(r, 'Speichern fehlgeschlagen'); $('#og-speichern').disabled = false; return; }
    S.d.dokumente[S.d.dokumente.findIndex((y) => y.id === x.id)] = r.data.dokument;
    G.knoten = kopie(offene(r.data.dokument).organigramm.knoten);
    G.geaendert = false;
    zeichnen(); felder();
    Q.oeffneDok(x.id);
    m.className = 'qm-meldung ok'; m.textContent = 'Organigramm gespeichert.';
  }
  /* Drucken: Diagramm ohne Bedienelemente auf A4 quer, eingepasst (Kopf mit Dokument und Stand) */
  function drucken() {
    let p = $('#print-root');
    if (!p) { p = document.createElement('div'); p.id = 'print-root'; document.body.append(p); }
    const [edit, wahl] = [G.edit, G.wahl];
    G.edit = false; G.wahl = '';
    p.innerHTML = `<div class="og-druck"><div class="og-druck-kopf"><b>${esc($('#og-titel').textContent)}</b><span>${esc($('#og-sub').textContent)}</span></div><div class="og-baum">${baumHtml()}</div></div>`;
    [G.edit, G.wahl] = [edit, wahl];
    p.style.cssText = 'display:block;position:absolute;left:-99999px;top:0';
    const b = $('.og-baum', p);
    b.style.zoom = Math.min(1, 1040 / b.offsetWidth, 620 / b.offsetHeight);
    p.style.cssText = '';
    document.body.classList.add('og-drucken');
    window.addEventListener('afterprint', () => { document.body.classList.remove('og-drucken'); p.innerHTML = ''; }, { once: true });
    window.print();
  }

  Q.organigramm = { karte };
})();
