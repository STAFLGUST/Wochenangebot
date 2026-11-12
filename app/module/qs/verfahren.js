/* STAFL-Plattform · Qualitätssicherung – Reiter „Verfahrensdoku“: Verfahrensdokumentation nach GoBD.
   Daten aus qs_verfahren (bei jedem Öffnen des Reiters frisch), Hilfen und Zustand über die Brücke window.STAFL_QS aus qs.js.
   Ansicht: Kopf mit Stand (letzte Fassung, Fortschritt, Änderungen seit der Fassung, Überprüfung), fünf Teile mit
   aufklappbaren Abschnitten (Frage aus dem Muster, Text, verknüpfte QM-Dokumente mit gültiger Version, IT-Systeme),
   Liste der IT-Systeme, Fassungen mit Änderungsliste und PDF.
   Dialoge: allgemeine Angaben, Abschnitt, IT-System, Freigabe (bzw. „ohne Änderung überprüft“), Export für Prüfungen
   (Zeitraum → PDF, auf Wunsch ZIP mit den QM-Dokumenten der damaligen Version; qs_verfahren_export).
   Rechte prüft der Server bei jeder Aktion (GR-103); ausgeblendete Knöpfe sind nur Anzeige. Kein Inline-Skript (CSP). */
'use strict';
(() => {
  const Q = window.STAFL_QS;
  if (!Q) return;
  const { $, $$, S, esc, api, senden, oeffne, toast, datum, wer, icon, chip, optionen } = Q;
  const V = { d: null, id: '', edit: {}, auf: new Set() };
  const darf = (r) => !!(V.d && V.d.rechte && V.d.rechte[r]);
  const doku = () => (V.d ? V.d.dokus.find((x) => x.id === V.id) || V.d.dokus[0] || null : null);
  const letzte = (d) => (d.fassungen.length ? d.fassungen[d.fassungen.length - 1] : null);
  const zeilen = (l) => l.map((z) => `<li>${esc(z)}</li>`).join('');

  /* ---------- Laden und Übernehmen ---------- */
  async function zeigen() {
    const r = await api('qs_verfahren');
    if (r.status === 401) { Q.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { toast(Q.fehlerText(r, 'Die Verfahrensdokumentation konnte nicht geladen werden'), true); return; }
    V.d = r.data;
    render();
  }
  function setze(dk) {
    const i = V.d.dokus.findIndex((x) => x.id === dk.id);
    if (i < 0) V.d.dokus.push(dk); else V.d.dokus[i] = dk;
    V.id = dk.id;
    render();
  }

  /* ---------- Ansicht ---------- */
  function render() {
    const d = doku(), b = darf('bearbeiten');
    $('#vf-leer').hidden = !!d; $('#vf-inhalt').hidden = !d;
    $('#vf-anlegen').hidden = !b; $('#vf-leer-hinweis').hidden = b;
    if (!d) return;
    V.id = d.id;
    const f = letzte(d), ab = d.seitFassung, u = d.ueberpruefung;
    const fertig = d.abschnitte.filter((a) => a.fertig).length, alle = d.abschnitte.length;
    const mehrere = V.d.dokus.length > 1 || b;
    $('#vf-wahl').hidden = !mehrere;
    $('#vf-wahl').innerHTML = V.d.dokus.map((x) => `<option value="${esc(x.id)}"${x.id === d.id ? ' selected' : ''}>${esc(x.gesellschaft || x.titel)}</option>`).join('')
      + (b ? '<option value="+">+ Weitere Dokumentation …</option>' : '');
    $('#vf-titel').textContent = d.titel;
    $('#vf-meta').innerHTML = [d.gesellschaft ? esc(d.gesellschaft) : '', d.verantwortlich ? 'Verantwortlich ' + wer(d.verantwortlich) : ''].filter(Boolean).join(' · ');
    $('#vf-kopf-aendern').hidden = !b;
    $('#vf-system-neu').hidden = !b;
    $('#vf-export').disabled = !f;
    $('#vf-export').title = f ? '' : 'Erst nach der ersten freigegebenen Fassung';
    const nurPruefen = !!f && !ab.offen;
    $('#vf-freigeben').hidden = !darf('freigeben');
    $('#vf-freigeben-text').textContent = nurPruefen ? 'Überprüft vermerken' : `Fassung ${f ? f.nr + 1 : 1} freigeben`;
    $('#vf-status').innerHTML = [
      f ? chip(`Fassung ${f.nr} · gültig ab ${datum(f.gueltigAb)}`, 'gruen') : chip('Noch keine Fassung freigegeben', 'gelb'),
      chip(`${fertig} von ${alle} Abschnitten fertig`, alle && fertig === alle ? 'gruen' : ''),
      f && ab.offen ? chip(`Arbeitsstand weicht von Fassung ${f.nr} ab`, 'gelb') : '',
      u ? chip(u.faellig ? `Überprüfung fällig seit ${datum(u.faelligAb)}` : `Nächste Überprüfung bis ${datum(u.faelligAb)}`, u.faellig ? 'rot' : '') : '',
    ].join('');
    $('#vf-offen').innerHTML = f && ab.offen ? zeilen(ab.zeilen) : '';
    renderTeile(d, b);
    renderSysteme(d, b);
    renderFassungen(d);
  }
  function verweisHtml(d, v) {
    const dk = Q.verweisDok(v);
    if (!dk) return `<span class="qm-verweis">${esc(v)}</span>`;
    const g = dk.eingezogen ? null : Q.gueltige(dk);
    const neu = d.seitFassung && d.seitFassung.dokumente.some((x) => x.dok === dk.id);
    return `<button class="qm-verweis" type="button" data-dok="${esc(dk.id)}" title="Dokument öffnen">${icon('dokument')}${esc(v)}${g ? ' · V' + esc(g.nr) : ' · ohne gültige Version'}${neu ? ' · seit der Fassung geändert' : ''}</button>`;
  }
  function renderTeile(d, b) {
    const geaendert = new Set(d.seitFassung ? d.seitFassung.abschnitte : []);
    const sysName = Object.fromEntries(d.systeme.map((s) => [s.id, s.name]));
    let html = '', n = 0;
    for (const [teil, name] of Object.entries(V.d.teile)) {
      n++;
      const liste = d.abschnitte.filter((a) => a.teil === teil);
      html += `<section class="qm-panel qm-glas vf-teil"><div class="qm-panelkopf"><h2><span class="vf-nr">${n}</span>${esc(name)}</h2>
        <div class="qm-filterzeile"><span class="qm-hilfe">${liste.filter((a) => a.fertig).length} von ${liste.length} fertig</span>${b ? `<button class="btn sm" type="button" data-vf-neu="${esc(teil)}">${icon('plus')}Abschnitt</button>` : ''}</div></div>`;
      liste.forEach((a, i) => {
        const systeme = a.systeme.map((id) => sysName[id]).filter(Boolean);
        html += `<details class="vf-abschnitt" data-id="${esc(a.id)}"${V.auf.has(a.id) ? ' open' : ''}>
          <summary><span class="vf-stand${a.fertig ? ' fertig' : ''}" title="${a.fertig ? 'fertig' : 'offen'}">${icon('haken')}</span><span class="vf-nr">${esc(a.nr)}</span><span class="vf-name">${esc(a.titel)}</span>
            <span class="qm-chips">${geaendert.has(a.id) ? chip('seit der Fassung geändert', 'gelb') : ''}${a.fertig ? '' : chip('offen', '')}</span></summary>
          <div class="vf-koerper">
            ${a.hinweis && !a.text ? `<p class="vf-frage"><b>Zu beschreiben:</b> ${esc(a.hinweis)}</p>` : ''}
            ${a.text ? `<p class="qm-text">${esc(a.text)}</p>` : ''}
            ${a.verweise.length ? `<div class="qm-verweise">${a.verweise.map((v) => verweisHtml(d, v)).join('')}</div>` : ''}
            ${a.zustaendig || systeme.length ? `<div class="qm-meta">${a.zustaendig ? `<span>Zuständig ${wer(a.zustaendig)}</span>` : ''}${systeme.length ? `<span>IT-Systeme: <b>${esc(systeme.join(', '))}</b></span>` : ''}</div>` : ''}
            ${b ? `<div class="vf-knoepfe"><button class="btn sm primary" type="button" data-vf-abschnitt="${esc(a.id)}">${icon('stift')}Bearbeiten</button>
              <button class="btn sm" type="button" data-vf-schieben="auf" data-id="${esc(a.id)}"${i === 0 ? ' disabled' : ''}>Nach oben</button>
              <button class="btn sm" type="button" data-vf-schieben="ab" data-id="${esc(a.id)}"${i === liste.length - 1 ? ' disabled' : ''}>Nach unten</button></div>` : ''}
          </div></details>`;
      });
      if (!liste.length) html += '<p class="qm-hilfe">Noch kein Abschnitt in diesem Teil.</p>';
      html += '</section>';
    }
    $('#vf-teile').innerHTML = html;
  }
  function renderSysteme(d, b) {
    $('#vf-systeme').innerHTML = d.systeme.map((s) => `<button class="vf-system${s.bis ? ' aus' : ''}" type="button" data-vf-system="${esc(s.id)}"${b ? '' : ' disabled'}>
      <b>${esc(s.name)}</b><span>${esc(V.d.systemArten[s.art] || s.art)} · ${esc(V.d.betrieb[s.betrieb] || s.betrieb)}${s.anbieter ? ' · ' + esc(s.anbieter) : ''}</span>
      ${s.zweck ? `<span>${esc(s.zweck.length > 140 ? s.zweck.slice(0, 140) + ' …' : s.zweck)}</span>` : ''}
      ${s.bis ? `<span>außer Betrieb seit ${esc(datum(s.bis))}</span>` : ''}</button>`).join('') || '<p class="qm-hilfe">Noch kein IT-System eingetragen.</p>';
  }
  function renderFassungen(d) {
    $('#vf-fassungen').innerHTML = d.fassungen.slice().reverse().map((f) => `<article class="vf-fassung">
      <div><b>Fassung ${f.nr}</b> <span class="qm-hilfe">gültig ab ${esc(datum(f.gueltigAb))}${f.gueltigBis ? ' bis ' + esc(datum(f.gueltigBis)) : ''}</span>
        <p>Freigegeben am ${esc(datum(f.datum))} von ${esc(f.von)} · Anlass: ${esc(f.grund)}</p></div>
      <button class="btn sm" type="button" data-vf-pdf="${f.nr}">${icon('dokument')}PDF</button>
      <details class="qm-details"><summary>Änderungen (${f.aenderungen.length})</summary><ul class="vf-zeilen">${zeilen(f.aenderungen)}</ul></details>
    </article>`).join('') || '<p class="qm-hilfe">Noch keine Fassung freigegeben. Sobald alle Abschnitte fertig sind, gibt die Geschäftsführung die erste Fassung frei.</p>';
    const p = d.pruefungen || [];
    if (p.length) $('#vf-fassungen').insertAdjacentHTML('beforeend', `<details class="qm-details"><summary>Ohne Änderung überprüft (${p.length})</summary><ul class="qm-verlauf">${p.slice().reverse().map((x) => `<li>${esc(datum(x.datum))} · ${esc(x.von)}${x.notiz ? ' – ' + esc(x.notiz) : ''}</li>`).join('')}</ul></details>`);
  }

  /* ---------- Export (PDF bzw. ZIP): lädt über fetch, damit Fehler als Text erscheinen ---------- */
  async function lade(query) {
    let res;
    try { res = await fetch('../../api/?action=qs_verfahren_export&doku=' + encodeURIComponent(V.id) + query, { credentials: 'same-origin', cache: 'no-store' }); } catch { return 'Keine Verbindung zum Server.'; }
    if (res.status === 401) { Q.zeigeAnmeldung(); return ''; }
    if (!res.ok) { let x = {}; try { x = await res.json(); } catch { /* keine JSON-Antwort */ } return x.error || `Export fehlgeschlagen (${res.status}).`; }
    const m = /filename\*=UTF-8''([^;]+)/.exec(res.headers.get('Content-Disposition') || '');
    Q.speichereDatei(await res.blob(), m ? decodeURIComponent(m[1]) : 'Verfahrensdokumentation');
    return null;
  }
  async function ladePdf(nr) {
    toast('Das PDF wird erstellt …');
    const f = await lade('&fassung=' + nr);
    if (f) toast(f, true);
  }

  /* ---------- Dialog: allgemeine Angaben ---------- */
  function oeffneKopf(neu) {
    const d = neu ? null : doku();
    V.edit.kopf = d;
    $('#vk-titel').textContent = d ? 'Allgemeine Angaben' : 'Dokumentation anlegen';
    $('#vk-titel-in').value = d ? d.titel : 'Verfahrensdokumentation Buchführung';
    $('#vk-gesellschaft').value = d ? d.gesellschaft : '';
    $('#vk-verantwortlich').value = d ? d.verantwortlich : '';
    $('#vk-muster-z').hidden = !!d; $('#vk-muster').checked = true;
    $('#vk-loeschen').hidden = !d || d.fassungen.length > 0;
    oeffne($('#dlg-vf-kopf'));
    $('#vk-titel-in').focus();
  }
  $('#vk-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const d = V.edit.kopf;
    const body = { titel: $('#vk-titel-in').value, gesellschaft: $('#vk-gesellschaft').value, verantwortlich: $('#vk-verantwortlich').value };
    if (d) { body.id = d.id; body.kopfRev = d.kopfRev; } else body.muster = $('#vk-muster').checked;
    const r = await senden(ev.target, 'qs_verfahren_save', body);
    if (!r) return;
    $('#dlg-vf-kopf').close();
    toast(d ? 'Angaben gespeichert' : 'Dokumentation angelegt');
    setze(r.doku);
  });
  $('#vk-loeschen').addEventListener('click', async () => {
    const d = V.edit.kopf, k = $('#vk-loeschen');
    if (!d) return;
    if (k.dataset.sicher !== d.id) { k.dataset.sicher = d.id; k.textContent = 'Wirklich löschen?'; return; }
    const r = await senden($('#vk-form'), 'qs_verfahren_save', { id: d.id, kopfRev: d.kopfRev, loeschen: true });
    if (!r) return;
    $('#dlg-vf-kopf').close();
    toast('Dokumentation gelöscht');
    V.id = '';
    await zeigen();
  });
  $('#dlg-vf-kopf').addEventListener('close', () => { delete $('#vk-loeschen').dataset.sicher; $('#vk-loeschen').textContent = 'Löschen'; });

  /* ---------- Dialog: Abschnitt ---------- */
  function oeffneAbschnitt(id, teil) {
    const d = doku(), a = id ? d.abschnitte.find((x) => x.id === id) : null;
    V.edit.abschnitt = a;
    $('#va-titel').textContent = a ? `Abschnitt ${a.nr} bearbeiten` : 'Abschnitt hinzufügen';
    $('#va-teil').innerHTML = optionen(V.d.teile, a ? a.teil : teil);
    $('#va-titel-in').value = a ? a.titel : ''; $('#va-text').value = a ? a.text : '';
    $('#va-verweise').value = a ? a.verweise.join('\n') : ''; $('#va-zust').value = a ? a.zustaendig : '';
    $('#va-fertig').checked = !!(a && a.fertig);
    $('#va-hinweis').hidden = !(a && a.hinweis);
    $('#va-hinweis').innerHTML = a && a.hinweis ? `<b>Zu beschreiben:</b> ${esc(a.hinweis)}` : '';
    $('#va-dok').innerHTML = '<option value="">Dokument wählen …</option>' + S.d.dokumente.filter((x) => x.nr && !x.eingezogen).sort((x, y) => Q.natCmp(x.nr, y.nr))
      .map((x) => `<option value="${esc(x.nr + ' ' + x.titel)}">${esc(x.nr + ' ' + x.titel)}</option>`).join('');
    const gewaehlt = new Set(a ? a.systeme : []);
    $('#va-systeme-z').hidden = !d.systeme.length;
    $('#va-systeme').innerHTML = d.systeme.map((s) => `<label class="qm-check"><input type="checkbox" value="${esc(s.id)}"${gewaehlt.has(s.id) ? ' checked' : ''}> ${esc(s.name)}</label>`).join('');
    $('#va-loeschen').hidden = !a;
    oeffne($('#dlg-vf-abschnitt'));
    (a ? $('#va-text') : $('#va-titel-in')).focus();
  }
  $('#va-dok').addEventListener('change', () => {
    const v = $('#va-dok').value, t = $('#va-verweise');
    if (v && !t.value.split('\n').map((x) => x.trim()).includes(v)) t.value = (t.value.trim() ? t.value.trim() + '\n' : '') + v;
    $('#va-dok').value = '';
  });
  $('#va-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const a = V.edit.abschnitt;
    const body = { doku: V.id, teil: $('#va-teil').value, titel: $('#va-titel-in').value, text: $('#va-text').value, verweise: $('#va-verweise').value, zustaendig: $('#va-zust').value,
      systeme: $$('#va-systeme input:checked').map((x) => x.value), fertig: $('#va-fertig').checked };
    if (a) { body.id = a.id; body.rev = a.rev; }
    const r = await senden(ev.target, 'qs_verfahren_abschnitt_save', body);
    if (!r) return;
    $('#dlg-vf-abschnitt').close();
    toast('Abschnitt gespeichert');
    setze(r.doku);
  });
  $('#va-loeschen').addEventListener('click', async () => {
    const a = V.edit.abschnitt, k = $('#va-loeschen');
    if (!a) return;
    if (k.dataset.sicher !== a.id) { k.dataset.sicher = a.id; k.textContent = 'Wirklich entfernen?'; return; }
    const r = await senden($('#va-form'), 'qs_verfahren_abschnitt_save', { doku: V.id, id: a.id, rev: a.rev, loeschen: true });
    if (!r) return;
    $('#dlg-vf-abschnitt').close();
    toast('Abschnitt entfernt');
    setze(r.doku);
  });
  $('#dlg-vf-abschnitt').addEventListener('close', () => { delete $('#va-loeschen').dataset.sicher; $('#va-loeschen').textContent = 'Entfernen'; });

  /* ---------- Dialog: IT-System ---------- */
  function oeffneSystem(id) {
    const s = id ? doku().systeme.find((x) => x.id === id) : null;
    V.edit.system = s;
    $('#vs-titel').textContent = s ? 'IT-System bearbeiten' : 'IT-System hinzufügen';
    $('#vs-art').innerHTML = optionen(V.d.systemArten, s ? s.art : 'vor');
    $('#vs-betrieb').innerHTML = optionen(V.d.betrieb, s ? s.betrieb : 'lokal');
    for (const [feld, sel] of [['name', '#vs-name'], ['zweck', '#vs-zweck'], ['anbieter', '#vs-anbieter'], ['zustaendig', '#vs-zust'], ['ort', '#vs-ort'], ['sicherung', '#vs-sicherung'],
      ['schnittstellen', '#vs-schnittstellen'], ['seit', '#vs-seit'], ['bis', '#vs-bis']]) $(sel).value = s ? s[feld] : '';
    $('#vs-loeschen').hidden = !s || s.inFassung;
    oeffne($('#dlg-vf-system'));
    $('#vs-name').focus();
  }
  $('#vs-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const s = V.edit.system;
    const body = { doku: V.id, name: $('#vs-name').value, art: $('#vs-art').value, zweck: $('#vs-zweck').value, anbieter: $('#vs-anbieter').value, zustaendig: $('#vs-zust').value,
      betrieb: $('#vs-betrieb').value, ort: $('#vs-ort').value, sicherung: $('#vs-sicherung').value, schnittstellen: $('#vs-schnittstellen').value, seit: $('#vs-seit').value, bis: $('#vs-bis').value };
    if (s) { body.id = s.id; body.rev = s.rev; }
    const r = await senden(ev.target, 'qs_verfahren_system_save', body);
    if (!r) return;
    $('#dlg-vf-system').close();
    toast('IT-System gespeichert');
    setze(r.doku);
  });
  $('#vs-loeschen').addEventListener('click', async () => {
    const s = V.edit.system, k = $('#vs-loeschen');
    if (!s) return;
    if (k.dataset.sicher !== s.id) { k.dataset.sicher = s.id; k.textContent = 'Wirklich entfernen?'; return; }
    const r = await senden($('#vs-form'), 'qs_verfahren_system_save', { doku: V.id, id: s.id, rev: s.rev, loeschen: true });
    if (!r) return;
    $('#dlg-vf-system').close();
    toast('IT-System entfernt');
    setze(r.doku);
  });
  $('#dlg-vf-system').addEventListener('close', () => { delete $('#vs-loeschen').dataset.sicher; $('#vs-loeschen').textContent = 'Entfernen'; });

  /* ---------- Dialog: Fassung freigeben oder „ohne Änderung überprüft“ ---------- */
  function oeffneFreigabe() {
    const d = doku(), f = letzte(d), nurPruefen = !!f && !d.seitFassung.offen;
    V.edit.freigabe = { d, nurPruefen };
    const offen = d.abschnitte.filter((a) => !a.fertig);
    $('#vg-titel').textContent = nurPruefen ? 'Ohne Änderung überprüft' : `Fassung ${f ? f.nr + 1 : 1} freigeben`;
    $('#vg-text').textContent = nurPruefen
      ? `Der Arbeitsstand entspricht der Fassung ${f.nr}. Mit dem Vermerk bestätigen Sie, dass die Dokumentation durchgesehen wurde und weiter dem tatsächlichen Ablauf entspricht. Die nächste Überprüfung ist dann in ${V.d.ueberpruefungMonate} Monaten fällig.`
      : offen.length ? `Noch nicht fertig: ${offen.slice(0, 4).map((a) => a.nr + ' ' + a.titel).join(', ')}${offen.length > 4 ? ` und ${offen.length - 4} weitere` : ''}. Bitte erst fertigstellen.`
        : 'Die Fassung hält den jetzigen Stand fest – mit der heute gültigen Version jedes verknüpften QM-Dokuments. Sie lässt sich danach nicht mehr ändern oder löschen.';
    $('#vg-zeilen').innerHTML = nurPruefen ? '' : zeilen(f ? d.seitFassung.zeilen : ['Erstfassung']);
    $('#vg-fassung').hidden = nurPruefen; $('#vg-notiz-z').hidden = !nurPruefen;
    $('#vg-grund').value = f ? '' : 'Erstfassung'; $('#vg-ab').value = V.d.heute; $('#vg-notiz').value = '';
    $('#vg-ok').textContent = nurPruefen ? 'Überprüfung vermerken' : 'Freigeben';
    $('#vg-ok').disabled = !nurPruefen && offen.length > 0;
    oeffne($('#dlg-vf-freigabe'));
  }
  $('#vg-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const { d, nurPruefen } = V.edit.freigabe;
    const body = nurPruefen ? { doku: d.id, rev: d.rev, ohneAenderung: true, notiz: $('#vg-notiz').value } : { doku: d.id, rev: d.rev, grund: $('#vg-grund').value, gueltigAb: $('#vg-ab').value };
    const r = await senden(ev.target, 'qs_verfahren_freigeben', body);
    if (!r) { await zeigen(); return; }
    $('#dlg-vf-freigabe').close();
    toast(nurPruefen ? 'Überprüfung vermerkt' : `Fassung ${letzte(r.doku).nr} freigegeben`);
    setze(r.doku);
  });

  /* ---------- Dialog: Export für Prüfungen ---------- */
  function enthalten() {
    const d = doku(), von = $('#ve-von').value, bis = $('#ve-bis').value;
    if (!von || !bis) { $('#ve-enthalten').textContent = ''; return; }
    const l = d.fassungen.filter((f) => f.gueltigAb <= bis && (!f.gueltigBis || f.gueltigBis >= von));
    $('#ve-enthalten').textContent = bis < von ? 'Der Zeitraum endet vor seinem Beginn.'
      : l.length ? `Im Zeitraum ${l.length === 1 ? 'galt Fassung' : 'galten die Fassungen'} ${l.map((f) => f.nr).join(', ')}.`
        : `Im Zeitraum galt noch keine Fassung (die erste gilt ab ${datum(d.fassungen[0].gueltigAb)}).`;
  }
  function oeffneExport() {
    const jahr = Number(V.d.heute.slice(0, 4));
    $('#ve-von').value = `${jahr - 3}-01-01`; $('#ve-bis').value = V.d.heute; $('#ve-dokumente').checked = false;
    oeffne($('#dlg-vf-export'));
    enthalten();
  }
  ['#ve-von', '#ve-bis'].forEach((s) => $(s).addEventListener('input', enthalten));
  $('#ve-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const knopf = ev.target.querySelector('[type="submit"]'), m = $('#ve-meldung');
    m.textContent = ''; knopf.disabled = true;
    const f = await lade(`&von=${encodeURIComponent($('#ve-von').value)}&bis=${encodeURIComponent($('#ve-bis').value)}${$('#ve-dokumente').checked ? '&dokumente=1' : ''}`);
    knopf.disabled = false;
    if (f) { m.textContent = f; return; }
    if (f === null) { $('#dlg-vf-export').close(); toast('Export heruntergeladen'); }
  });

  /* ---------- Knöpfe ---------- */
  $('#vf-anlegen').addEventListener('click', () => oeffneKopf(true));
  $('#vf-kopf-aendern').addEventListener('click', () => oeffneKopf(false));
  $('#vf-wahl').addEventListener('change', () => { const v = $('#vf-wahl').value; if (v === '+') { $('#vf-wahl').value = V.id; oeffneKopf(true); } else { V.id = v; render(); } });
  $('#vf-entwurf').addEventListener('click', () => ladePdf(0));
  $('#vf-export').addEventListener('click', oeffneExport);
  $('#vf-freigeben').addEventListener('click', oeffneFreigabe);
  $('#vf-system-neu').addEventListener('click', () => oeffneSystem(''));
  $('#vf-systeme').addEventListener('click', (ev) => { const b = ev.target.closest('[data-vf-system]'); if (b) oeffneSystem(b.dataset.vfSystem); });
  $('#vf-fassungen').addEventListener('click', (ev) => { const b = ev.target.closest('[data-vf-pdf]'); if (b) ladePdf(b.dataset.vfPdf); });
  $('#vf-teile').addEventListener('toggle', (ev) => { const t = ev.target; if (t.matches && t.matches('.vf-abschnitt')) { if (t.open) V.auf.add(t.dataset.id); else V.auf.delete(t.dataset.id); } }, true);
  $('#vf-teile').addEventListener('click', async (ev) => {
    const dk = ev.target.closest('[data-dok]'); if (dk) { Q.oeffneDok(dk.dataset.dok); return; }
    const neu = ev.target.closest('[data-vf-neu]'); if (neu) { oeffneAbschnitt('', neu.dataset.vfNeu); return; }
    const a = ev.target.closest('[data-vf-abschnitt]'); if (a) { oeffneAbschnitt(a.dataset.vfAbschnitt); return; }
    const s = ev.target.closest('[data-vf-schieben]');
    if (s) {
      s.disabled = true;
      const r = await api('qs_verfahren_ordnen', { doku: V.id, id: s.dataset.id, richtung: s.dataset.vfSchieben });
      if (r.status === 200 && r.data.ok) setze(r.data.doku); else { toast(Q.fehlerText(r, 'Verschieben fehlgeschlagen'), true); await zeigen(); }
    }
  });

  Q.verfahren = { zeigen };
})();
