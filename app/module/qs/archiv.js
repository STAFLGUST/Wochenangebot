/* STAFL-Plattform · QM-System: Archiv der Ordner und externen Dokumente (Ordnerbaum in der Seitenleiste) und Eingang (Dateien
   ohne Ziel: hochladen, zuordnen, löschen). Daten erst beim Öffnen: qs_archiv (Ordner) bzw. qs_eingang (Dateien und erlaubte Ziele);
   Herunterladen über direkte Links (qs_datei, qs_archiv_zip). Regeln nur auf dem Server (docs/entwickler/05-daten.md). Nutzt die
   Brücke window.STAFL_QS aus qs.js und trägt sich als STAFL_QS.archiv ein. */
'use strict';
(() => {
  const Q = window.STAFL_QS;
  const { $, $$, S, esc, api, toast, fehlerText, zeigeAnmeldung, icon, natCmp, dateienText } = Q;
  const SU = window.STAFL_SUCHE;
  const API = '../../api/';
  const ZEILEN = 500;   // höchstens so viele Zeilen je Suche bzw. Liste
  const OHNE_ORDNER = '/';   // „/“ kommt in keinem Ordnernamen vor
  const B = { dok: '', dateien: null, q: '' };   // Ordnerbaum des offenen Dokuments
  const E = { dateien: null, wahl: new Set(), ziele: new Map() };   // Eingang; ziele: Beschriftung → {dok, ver} (vom Server erlaubt)
  const link = (q) => API + '?action=' + q;
  const pfadText = (p) => (p ? p.split('/').join(' / ') : '');

  /* ---------- Ordnerbaum: Map pfad → Knoten, <details> erst beim Aufklappen gefüllt ---------- */
  function baumBauen(dateien) {
    const wurzel = { name: '', pfad: '', kinder: new Map(), dateien: [], n: 0, b: 0 };
    for (const f of dateien) {
      if (f.entfernt) continue;
      let k = wurzel;
      k.n++; k.b += f.groesse;
      for (const t of f.pfad ? f.pfad.split('/') : []) {
        if (!k.kinder.has(t)) k.kinder.set(t, { name: t, pfad: k.pfad ? `${k.pfad}/${t}` : t, kinder: new Map(), dateien: [], n: 0, b: 0 });
        k = k.kinder.get(t); k.n++; k.b += f.groesse;
      }
      k.dateien.push(f);
    }
    return wurzel;
  }
  const zipLink = (pfad) => `<a class="qm-baum-zip" href="${esc(link(`qs_archiv_zip&dok=${encodeURIComponent(B.dok)}${pfad ? '&pfad=' + encodeURIComponent(pfad) : ''}`))}" download title="Als ZIP herunterladen">${icon('download')}ZIP</a>`;
  function dateiZeile(f, offen, mitPfad) {
    return `<li class="qm-datei"><button class="qm-datei-name" type="button" data-datei="${esc(f.id)}" title="${esc(f.name)} herunterladen">${icon('dokument')}<span>${esc(f.name)}</span></button>`
      + `<span class="qm-sub">${mitPfad && f.pfad ? esc(pfadText(f.pfad)) + ' · ' : ''}${esc(Q.groesseText(f.groesse))}${f.hochgeladen && f.hochgeladen.von ? ` · ${esc(f.hochgeladen.von)} · ${esc(window.STAFL_FORMAT.datum(f.hochgeladen.t))}` : ''}</span>`
      + `${offen ? `<button class="qm-datei-weg" type="button" data-datei-weg="${esc(f.id)}" aria-label="${esc(f.name)} entfernen" title="Entfernen">×</button>` : ''}</li>`;
  }
  function knotenInhalt(k, offen) {
    const ordner = [...k.kinder.values()].sort((a, b) => natCmp(a.name, b.name));
    const dateien = k.dateien.slice().sort((a, b) => natCmp(a.name, b.name));
    return ordner.map((u) => `<details class="qm-baum-ordner" data-pfad="${esc(u.pfad)}"><summary>${icon('ordner')}<span class="qm-baum-name">${esc(u.name)}</span>`
        + `<span class="qm-sub">${dateienText(u.n)} · ${esc(Q.groesseText(u.b))}</span>${zipLink(u.pfad)}</summary></details>`).join('')
      + (dateien.length ? `<ul class="qm-dateien">${dateien.slice(0, ZEILEN).map((f) => dateiZeile(f, offen, false)).join('')}</ul>` : '')
      + (dateien.length > ZEILEN ? `<p class="qm-hilfe">Angezeigt: ${Q.zahl(ZEILEN)} von ${Q.zahl(dateien.length)} Dateien – die Suche grenzt ein.</p>` : '');
  }
  function baumZeichnen() {
    const el = $('#dk-baum');
    if (!el || el.dataset.baum !== B.dok) return;
    const x = S.d.dokumente.find((y) => y.id === B.dok);
    if (!x || B.dateien === null) { el.innerHTML = '<p class="qm-hilfe">Wird geladen …</p>'; return; }
    const offen = !x.eingezogen && Q.darf('bearbeiten'), alle = B.dateien.filter((f) => !f.entfernt), weg = B.dateien.filter((f) => f.entfernt);
    if (!alle.length && !weg.length) { el.innerHTML = '<p class="qm-hilfe">Noch keine Dateien.</p>'; return; }
    const w = baumBauen(B.dateien);
    let h = `<div class="qm-baum-kopf"><input class="qm-eingabe qm-suche" type="search" id="dk-baum-suche" placeholder="Datei oder Ordner suchen" aria-label="Im Ordner suchen" value="${esc(B.q)}">`
      + `<span class="qm-sub">${dateienText(w.n)} · ${esc(Q.groesseText(w.b))}</span>${w.n ? zipLink('') : ''}</div><div id="dk-baum-inhalt"></div>`;
    if (weg.length) h += `<details class="qm-details qm-entfernt"><summary>${weg.length === 1 ? '1 Datei entfernt' : Q.zahl(weg.length) + ' Dateien entfernt'}</summary><ul class="qm-verlauf">${weg.slice(0, ZEILEN).map((f) => `<li><s>${esc(f.name)}</s>${f.pfad ? ' · ' + esc(pfadText(f.pfad)) : ''} · ${esc(Q.zeitpunkt(f.entfernt.t))} · ${esc(f.entfernt.von)}: ${esc(f.entfernt.grund)}</li>`).join('')}</ul></details>`;
    el.innerHTML = h;
    inhaltZeichnen(w, offen);
  }
  function inhaltZeichnen(w, offen) {
    const ziel = $('#dk-baum-inhalt');
    if (!ziel) return;
    if (!B.q) { ziel.innerHTML = knotenInhalt(w, offen); B.knoten = w; return; }
    const q = SU.woerter(B.q), treffer = B.dateien.filter((f) => !f.entfernt && SU.passt(q, SU.heu(f.name, f.pfad)));
    ziel.innerHTML = treffer.length ? `<ul class="qm-dateien">${treffer.slice(0, ZEILEN).map((f) => dateiZeile(f, offen, true)).join('')}</ul>`
      + (treffer.length > ZEILEN ? `<p class="qm-hilfe">Angezeigt: ${Q.zahl(ZEILEN)} von ${Q.zahl(treffer.length)} Treffern.</p>` : '') : '<p class="qm-hilfe">Keine passenden Dateien.</p>';
  }
  async function baumLaden(dok) {
    B.dok = dok; B.dateien = null; B.q = '';
    const r = await api('qs_archiv', null, '&dok=' + encodeURIComponent(dok));
    if (B.dok !== dok) return;
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Dateien nicht geladen'), true); B.dateien = []; }
    else B.dateien = r.data.dateien;
    baumZeichnen();
  }
  /* HTML des Ordnerbaums für die Seitenleiste (qs.js renderDok); lädt beim ersten Öffnen eines Dokuments */
  function baumHtml(x) {
    if (B.dok !== x.id) { B.dok = x.id; B.dateien = null; setTimeout(() => baumLaden(x.id)); }
    else if (B.dateien !== null) setTimeout(baumZeichnen);
    return `<div class="qm-baum" id="dk-baum" data-baum="${esc(x.id)}"><p class="qm-hilfe">Wird geladen …</p></div>`;
  }
  /* Nach Hochladen/Entfernen neu laden: Eingang bzw. Ordner des Dokuments */
  async function neu(dok) {
    if (dok === 'eingang') { if (E.dateien !== null) { await ladeEingang(); eingangZeichnen(); } return; }
    if (dok === B.dok) await baumLaden(dok);
  }
  const ort = (x, id) => { const f = x.id === B.dok && B.dateien ? B.dateien.find((y) => y.id === id) : null; return f ? { f, v: null } : null; };
  // <details> füllen, sobald sie aufgehen („toggle“ steigt nicht auf – daher in der Erfassungsphase)
  document.addEventListener('toggle', (ev) => {
    const d = ev.target;
    if (!d.matches || !d.matches('.qm-baum-ordner') || !d.open || d.dataset.gefuellt || !B.knoten) return;
    let k = B.knoten;
    for (const t of d.dataset.pfad.split('/')) k = k && k.kinder.get(t);
    if (!k) return;
    const x = S.d.dokumente.find((y) => y.id === B.dok);
    d.insertAdjacentHTML('beforeend', `<div class="qm-baum-inhalt">${knotenInhalt(k, !!x && !x.eingezogen && Q.darf('bearbeiten'))}</div>`);
    d.dataset.gefuellt = '1';
  }, true);
  $('#qm-dk').addEventListener('input', (ev) => {
    if (ev.target.id !== 'dk-baum-suche') return;
    B.q = ev.target.value;
    const x = S.d.dokumente.find((y) => y.id === B.dok);
    inhaltZeichnen(baumBauen(B.dateien || []), !!x && !x.eingezogen && Q.darf('bearbeiten'));
  });

  /* ---------- Eingang (nur mit „bearbeiten“): Liste lädt erst beim Öffnen (bis 20 000 Dateien), angezeigt höchstens ZEILEN;
     Suche (Name und Ordnerpfad) und Ordner der ersten Ebene grenzen ein, „alle“ wählt alle gefilterten. Ziele liefert der Server. ---------- */
  const ordnerVon = (f) => (f.pfad ? f.pfad.split('/')[0] : OHNE_ORDNER);
  async function ladeEingang() {
    const r = await api('qs_eingang');
    if (r.status === 401) { zeigeAnmeldung(); return false; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Eingang nicht geladen'), true); return false; }
    E.dateien = r.data.dateien.slice().reverse();   // neueste zuerst
    const da = new Set(E.dateien.map((f) => f.id));
    for (const id of [...E.wahl]) if (!da.has(id)) E.wahl.delete(id);
    eingangZiele(r.data.ziele);
    return true;
  }
  function eingangSicht() {
    const q = SU.woerter($('#ei-suche').value), o = $('#ei-ordner').value;
    return (E.dateien || []).filter((f) => (!o || ordnerVon(f) === o) && SU.passt(q, SU.heu(f.name, f.pfad)));
  }
  function eingangZiele(ziele) {
    const dok = new Map(S.d.dokumente.map((x) => [x.id, x]));
    E.ziele = new Map();
    for (const z of ziele.filter((y) => dok.has(y.dok)).sort((a, b) => { const x = dok.get(a.dok), y = dok.get(b.dok); return natCmp(x.kapitel, y.kapitel) || natCmp(x.nr, y.nr) || natCmp(x.titel, y.titel); })) {
      const x = dok.get(z.dok), basis = `${x.nr ? x.nr + ' · ' : ''}${x.titel} (${x.kapitel})${z.ver ? ' – Entwurf' : ''}`;
      let text = basis;
      for (let n = 2; E.ziele.has(text); n++) text = `${basis} ${n}`;   // gleiche Titel bleiben unterscheidbar
      E.ziele.set(text, z);
    }
    $('#ei-ziele').innerHTML = [...E.ziele.keys()].map((k) => `<option value="${esc(k)}"></option>`).join('');
  }
  const eingangZiel = () => E.ziele.get($('#ei-ziel').value) || null;
  function eingangKnoepfe() {
    const n = E.wahl.size, k = $('#ei-loeschen');
    $('#ei-gewaehlt').textContent = n ? `${dateienText(n)} ausgewählt` : 'Dateien auswählen, dann ein Ziel wählen';
    $('#ei-zuordnen').disabled = !n || !eingangZiel();
    k.disabled = !n;
    if (!k.dataset.sicher) k.textContent = n ? `${dateienText(n)} löschen` : 'Löschen';
  }
  function eingangZeichnen() {
    if (!$('#dlg-eingang').open) return;
    const alle = E.dateien || [], a = S.d.ablage || { max: 0, eingang: 0 };
    $('#ei-max').textContent = ` · bis ${Q.zahl(Math.round(a.max / 1048576))} MB je Datei, höchstens ${Q.zahl(a.eingang)} Dateien`;
    $('#ei-laden').innerHTML = Q.ladenHtml({ id: 'eingang' }, '');
    $('#ei-titel').textContent = E.dateien ? `Eingang · ${dateienText(alle.length)}` : 'Eingang';
    const je = new Map();
    for (const f of alle) je.set(ordnerVon(f), (je.get(ordnerVon(f)) || 0) + 1);
    const w = $('#ei-ordner').value;
    $('#ei-ordner').innerHTML = '<option value="">Alle Ordner</option>' + [...je].sort((x, y) => (x[0] === OHNE_ORDNER) - (y[0] === OHNE_ORDNER) || natCmp(x[0], y[0]))
      .map(([o, n]) => `<option value="${esc(o)}">${esc(o === OHNE_ORDNER ? 'ohne Ordner' : o)} (${Q.zahl(n)})</option>`).join('');
    $('#ei-ordner').value = je.has(w) ? w : '';
    const sicht = eingangSicht(), gew = sicht.filter((f) => E.wahl.has(f.id)).length;
    const zeile = (f) => `<tr data-ei="${esc(f.id)}"><td class="qm-sa-an"><input type="checkbox" data-ei-an="${esc(f.id)}"${E.wahl.has(f.id) ? ' checked' : ''} aria-label="${esc(f.name)} auswählen"></td>
      <td class="qm-voll" data-label="Datei"><button class="qm-datei-name" type="button" data-ei-datei="${esc(f.id)}" title="${esc(f.name)} herunterladen">${icon('dokument')}<span>${esc(f.name)}</span></button><span class="qm-sub">${esc(Q.groesseText(f.groesse))}</span></td>
      <td data-label="Ordner" class="qm-ei-pfad">${f.pfad ? esc(pfadText(f.pfad)) : '<span class="qm-null">—</span>'}</td>
      <td data-label="Hochgeladen">${esc(f.hochgeladen.von)}<span class="qm-sub">${esc(Q.zeitpunkt(f.hochgeladen.t))}</span></td></tr>`;
    $('#ei-liste').innerHTML = E.dateien === null ? '<p class="qm-hilfe">Wird geladen …</p>'
      : `<table class="qm-tabelle qm-karten qm-sa-tabelle qm-ei-tabelle"><thead><tr><th class="qm-sa-an"><input type="checkbox" id="ei-alle" aria-label="Alle ${Q.zahl(sicht.length)} auswählen"${sicht.length && gew === sicht.length ? ' checked' : ''}></th><th>Datei</th><th>Ordner</th><th>Hochgeladen</th></tr></thead>`
        + `<tbody>${sicht.slice(0, ZEILEN).map(zeile).join('') || Q.leerzeile(4, alle.length ? 'Keine passenden Dateien.' : 'Der Eingang ist leer.')}</tbody></table>`
        + (sicht.length > ZEILEN ? `<p class="qm-hilfe">Angezeigt: ${Q.zahl(ZEILEN)} von ${Q.zahl(sicht.length)} – Suche oder Ordner grenzen ein; „alle“ wählt alle ${Q.zahl(sicht.length)}.</p>` : '');
    eingangKnoepfe();
  }
  async function oeffneEingang() {
    eingangZiele([]);
    E.dateien = null; E.wahl.clear();
    if (S.laden && S.laden.fertig) S.laden = null;
    $('#ei-ziel').value = ''; $('#ei-suche').value = ''; $('#ei-ordner').value = ''; $('#ei-meldung').textContent = ''; delete $('#ei-loeschen').dataset.sicher;
    Q.oeffne($('#dlg-eingang'));
    eingangZeichnen();
    if (await ladeEingang()) eingangZeichnen();
  }
  function eingangWeg(ids) {
    const weg = new Set(ids);
    E.dateien = E.dateien.filter((f) => !weg.has(f.id));
    E.wahl.clear();
  }
  function eingangFehler(r, text) {
    if (r.status === 401) { zeigeAnmeldung(); return true; }
    if (r.status === 200 && r.data.ok) return false;
    $('#ei-meldung').className = 'qm-meldung'; $('#ei-meldung').textContent = fehlerText(r, text);
    eingangKnoepfe();
    return true;
  }
  $('#qm-d-eingang').addEventListener('click', oeffneEingang);
  $$('#dlg-eingang [data-ei-zu]').forEach((k) => k.addEventListener('click', () => $('#dlg-eingang').close()));
  ['#ei-suche', '#ei-ordner'].forEach((sel) => $(sel).addEventListener('input', eingangZeichnen));
  $('#ei-ziel').addEventListener('input', () => { $('#ei-ziel').removeAttribute('aria-invalid'); eingangKnoepfe(); });
  $('#ei-drop').addEventListener('click', () => Q.waehleDateien('', 'eingang'));
  $('#ei-drop').addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); Q.waehleDateien('', 'eingang'); } });
  $('#ei-liste').addEventListener('change', (ev) => {
    const c = ev.target;
    if (c.id === 'ei-alle') for (const f of eingangSicht()) { if (c.checked) E.wahl.add(f.id); else E.wahl.delete(f.id); }
    else if (c.dataset.eiAn) { if (c.checked) E.wahl.add(c.dataset.eiAn); else E.wahl.delete(c.dataset.eiAn); }
    else return;
    delete $('#ei-loeschen').dataset.sicher;
    eingangZeichnen();
  });
  $('#ei-liste').addEventListener('click', (ev) => { const d = ev.target.closest('[data-ei-datei]'); if (d) Q.herunterladen(d.dataset.eiDatei); });
  $('#ei-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const z = eingangZiel(), ids = [...E.wahl], name = $('#ei-ziel').value;
    if (!z) { $('#ei-ziel').setAttribute('aria-invalid', 'true'); return; }
    if (!ids.length) return;
    $('#ei-zuordnen').disabled = true;
    const r = await api('qs_datei_zuordnen', { dateien: ids, dokument: z.dok, version: z.ver });
    if (eingangFehler(r, 'Zuordnen fehlgeschlagen')) return;
    eingangWeg(ids);
    $('#ei-ziel').value = ''; $('#ei-meldung').textContent = '';
    toast(`${dateienText(ids.length)} zugeordnet: ${name}`);
    if (z.dok === B.dok) B.dok = '';
    await Q.neuLaden();
    if (await ladeEingang()) eingangZeichnen();
  });
  $('#ei-loeschen').addEventListener('click', async () => {
    const k = $('#ei-loeschen'), ids = [...E.wahl];
    if (!ids.length) return;
    if (!k.dataset.sicher) { k.dataset.sicher = '1'; k.textContent = `${dateienText(ids.length)} endgültig löschen?`; return; }
    delete k.dataset.sicher; k.disabled = true;
    const r = await api('qs_eingang_loeschen', { dateien: ids });
    if (eingangFehler(r, 'Löschen fehlgeschlagen')) return;
    eingangWeg(ids);
    $('#ei-meldung').textContent = '';
    toast(`${dateienText(ids.length)} gelöscht`);
    await Q.neuLaden();
  });

  Q.archiv = { baumHtml, neu, ort, eingangZeichnen };
})();
