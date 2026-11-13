/* STAFL-Plattform · Angebot · Reiter „Sonderangebote“ im Eingabebereich (unter „Einzelangebote“, Auftrag des Inhabers 13.11.2026).
   Ein Sonderangebot gilt immer für ganze Kundengruppen und hat eine Gültigkeit: Zeitraum (von–bis) oder Kalenderwoche – im
   Fenster „Sonderangebot“ mit einem Kippschalter umschaltbar. Die Artikel bearbeitet man im gewohnten Editor („Artikel
   bearbeiten“ öffnet „Angebot bearbeiten“ mit diesem Angebot): Artikel hinzufügen, Preise, Werbung, „Aus anderem Angebot“
   (einzelne Artikel aus Wochen- oder Kundenangeboten übernehmen). Veröffentlicht wird wie immer im Modul Versand.
   Liste nach Stand: läuft, geplant, abgelaufen/beendet (abgelaufene bleiben gespeichert, bis jemand sie löscht) – je Karte
   Gültigkeit, Kundengruppen, Artikel im Entwurf/veröffentlicht und (nur mit „Kunden ansehen“) die Zahl der Kunden.
   Server: Aktionen sonderangebote, sonderangebot_save (angebote.verwalten), sonderangebot_loeschen (angebote.loeschen mit
   Bestätigung) in api/aktionen/angebote.php, Regeln in api/module/angebot/sonderangebote.php. Kunden sehen ein Sonderangebot
   nur in seiner Gültigkeit, nur über ihre Kundengruppe und erst nach dem Veröffentlichen – das entscheidet allein der Server.
   Wird von admin/index.html nach admin.js geladen (nutzt window.WA, Angebotsliste über WA.angebot.sonder). */
(function () {
  'use strict';
  const W = window.WA;
  const host = document.getElementById('view-sonder');
  const dlg = document.getElementById('dlg-sonder');
  if (!W || !host || !dlg || !W.angebot || !W.angebot.sonder) return;
  const { $, $$, api, esc, icon, toast, confirmBox, dateTime, plural, fmtInt, SU, may } = W;
  const S = W.angebot.sonder;
  const body = document.getElementById('sonder-body');
  const STAND = { laeuft: 'läuft', geplant: 'geplant', beendet: 'beendet', abgelaufen: 'abgelaufen' };
  const VERSAND = /(^|\.)dashboard-stafl\.de$/.test(location.hostname) ? 'https://versand.dashboard-stafl.de/' : '../module/versand/';
  const iso = (d) => d.toLocaleDateString('sv-SE');   // Ortszeit (toISOString wäre UTC)
  const plus = (tage, ab) => { const d = ab ? new Date(ab + 'T12:00:00') : new Date(); d.setDate(d.getDate() + tage); return iso(d); };
  const dmy = (s) => (s ? s.slice(8, 10) + '.' + s.slice(5, 7) + '.' + s.slice(0, 4) : '');
  const wt = (s) => ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'][new Date(s + 'T12:00:00').getDay()];
  /* ISO-Kalenderwoche eines Tages und Montag/Sonntag einer KW (wie der Server, ISO 8601) */
  function kwVon(s) {
    const d = new Date(s + 'T12:00:00'); const t = (d.getDay() + 6) % 7; d.setDate(d.getDate() - t + 3);
    const j = d.getFullYear(), j4 = new Date(j, 0, 4, 12);
    return { jahr: j, kw: 1 + Math.round(((d - j4) / 864e5 - 3 + ((j4.getDay() + 6) % 7)) / 7) };
  }
  const kwTage = (kw, jahr) => window.OfferCore.isoWeekRange(kw, jahr);
  const kwGibt = (kw, jahr) => kw >= 1 && kw <= kwVon(jahr + '-12-28').kw;

  let d = null;          // Antwort von sonderangebote: { rev, heute, sonder: [...], gruppen: [...], kundenZahl }
  let q = '';
  let ed = null;         // Fenster: { id, name, modus, von, bis, kw, jahr, gruppen: Set, gq }
  let busy = false;
  const darf = () => may('angebote.verwalten');

  async function laden() { d = await api('sonderangebote'); }
  async function render() {
    if (!d) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Sonderangebote werden geladen …</div>';
    try { await laden(); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    liste();
  }
  const gName = (nr) => ((d.gruppen || []).find((g) => g.nr === nr) || {}).name || '';
  const chips = (gr) => gr.map((nr) => `<span class="of-chip${d.gruppen.length && !gName(nr) ? ' fremd' : ''}" title="${esc(gName(nr) || (d.gruppen.length ? 'Kundengruppe nicht mehr vorhanden' : 'Kundengruppe'))}">${esc(nr)}${gName(nr) ? ' · ' + esc(gName(nr)) : ''}</span>`).join('');

  /* ---------- Liste ---------- */
  function karte(z) {
    const neuer = z.artikel !== z.veroeffentlicht;
    const hinweis = !z.artikel ? `${icon('info', 'sm')}<span>Noch keine Artikel – „Artikel bearbeiten“ und hinzufügen oder aus einem anderen Angebot übernehmen.</span>`
      : !z.veroeffentlicht ? `${icon('info', 'sm')}<span>Noch nicht veröffentlicht – Kunden sehen es erst danach.${may('versand.zugang') ? ` <a href="${VERSAND}">Zum Versand</a>` : ''}</span>`
        : neuer && ['laeuft', 'geplant'].includes(z.status) ? `${icon('info', 'sm')}<span>Änderungen im Entwurf – Kunden sehen sie nach dem Veröffentlichen.${may('versand.zugang') ? ` <a href="${VERSAND}">Zum Versand</a>` : ''}</span>` : '';
    const akt = [`<button type="button" class="btn sm" data-so="editor">${icon('tag', 'sm')}Artikel bearbeiten</button>`];
    if (darf()) {
      akt.push(`<button type="button" class="btn sm ghost" data-so="einstellungen">${icon('calendar', 'sm')}Gültigkeit und Gruppen</button>`);
      if (z.status === 'laeuft' || z.status === 'geplant') akt.push(`<button type="button" class="btn sm ghost" data-so="beenden" title="Sofort für Kunden ausblenden – bleibt gespeichert">${icon('x', 'sm')}Beenden</button>`);
      if (z.status === 'beendet') akt.push(`<button type="button" class="btn sm ghost" data-so="fortsetzen" title="Im Zeitraum wieder für Kunden sichtbar">${icon('undo', 'sm')}Fortsetzen</button>`);
    }
    if (may('angebote.loeschen')) akt.push(`<button type="button" class="ibtn danger" data-so="loeschen" aria-label="Sonderangebot ${esc(z.name)} löschen" title="Löschen">${icon('trash')}</button>`);
    const g = z.gueltig || {};
    const zeit = g.modus === 'kw' ? `<strong>KW ${esc(g.kw)}/${esc(g.jahr)}</strong> <span class="muted">· ${wt(z.von)} ${esc(dmy(z.von).slice(0, 6))} – ${wt(z.bis)} ${esc(dmy(z.bis))}</span>`
      : `<strong>${esc(dmy(z.von))} – ${esc(dmy(z.bis))}</strong>`;
    return `<article class="so-k st-${esc(z.status)}" data-so-id="${esc(z.id)}">
      <div class="so-kopf"><h3>${esc(z.name)}</h3><span class="so-st ${esc(z.status)}">${esc(STAND[z.status] || z.status)}</span></div>
      <p class="so-zeit">${icon('calendar', 'sm')}<span>${zeit}</span></p>
      <div class="so-gr" aria-label="Kundengruppen">${icon('users', 'sm')}<div class="of-chips">${chips(z.gruppen)}</div></div>
      <dl class="so-zahlen"><div><dt>Artikel</dt><dd>${fmtInt.format(z.artikel)}</dd></div><div><dt>veröffentlicht</dt><dd>${fmtInt.format(z.veroeffentlicht)}</dd></div>
        ${d.kundenZahl ? `<div><dt>Kunden</dt><dd>${fmtInt.format(z.kunden || 0)}</dd></div>` : ''}</dl>
      ${hinweis ? `<p class="so-hinweis">${hinweis}</p>` : ''}
      ${z.beendet ? `<p class="sub">Beendet ${esc(dateTime(z.beendet.t))} von ${esc(z.beendet.von || '')}</p>` : ''}
      <div class="so-akt">${akt.join('')}</div></article>`;
  }
  function liste() {
    const toks = SU.woerter(q);
    const l = d.sonder.filter((z) => SU.passt(toks, SU.heu(z.name, STAND[z.status], z.text, ...z.gruppen, ...z.gruppen.map(gName))));
    const teil = (st) => l.filter((z) => st.includes(z.status)).sort((a, b) => (a.von < b.von ? -1 : a.von > b.von ? 1 : a.name.localeCompare(b.name, 'de')));
    const laeuft = teil(['laeuft']), geplant = teil(['geplant']), vorbei = teil(['abgelaufen', 'beendet']).reverse();
    const block = (titel, arr, cls) => (arr.length ? `<section class="so-sec ${cls}" aria-label="${esc(titel)}"><h2 class="so-h">${esc(titel)} <small>${fmtInt.format(arr.length)}</small></h2><div class="so-grid">${arr.map(karte).join('')}</div></section>` : '');
    host.innerHTML = `
      <div class="ed-toolbar so-bar">
        <div class="search">${icon('search')}<input id="so-q" type="search" autocomplete="off" placeholder="Sonderangebote finden: Name, Kundengruppe …" aria-label="Sonderangebote suchen" value="${esc(q)}"></div>
        <span class="ed-hint">${plural(l.length, 'Sonderangebot', 'Sonderangebote')}</span>
        ${darf() ? `<button type="button" class="btn primary" id="so-neu">${icon('plus')}Neues Sonderangebot</button>` : ''}
      </div>
      <p class="so-info">${icon('info', 'sm')}<span>Ein Sonderangebot gilt für ganze Kundengruppen – zusätzlich zu deren Wochen- bzw. Kundenangebot. Kunden der Gruppen sehen es nur im gewählten Zeitraum bzw. in der Kalenderwoche und erst nach dem Veröffentlichen; nie auf der öffentlichen Seite.</span></p>
      ${!d.sonder.length ? `<div class="ed-empty"><h3>Noch keine Sonderangebote</h3><p>${darf() ? '„Neues Sonderangebot“: Name, Kundengruppen und Gültigkeit wählen, danach die Artikel wie gewohnt im Editor bearbeiten.' : 'Sonderangebote legen Mitarbeiter mit dem Recht „Kundenangebote anlegen“ an.'}</p></div>`
        : !l.length ? '<div class="ed-empty"><h3>Keine Treffer</h3><p>Suchbegriff anpassen.</p></div>'
          : block('Laufen gerade', laeuft, 'laeuft') + block('Geplant', geplant, 'geplant')
            + (vorbei.length ? `<details class="so-sec vorbei"${laeuft.length + geplant.length ? '' : ' open'}><summary class="so-h">Abgelaufen und beendet <small>${fmtInt.format(vorbei.length)}</small></summary><div class="so-grid">${vorbei.map(karte).join('')}</div></details>` : '')}`;
  }
  host.addEventListener('input', (e) => {
    if (e.target.id !== 'so-q') return;
    q = e.target.value; liste();
    const i = $('#so-q'); i.focus(); i.setSelectionRange(i.value.length, i.value.length);
  });
  host.addEventListener('click', async (e) => {
    if (e.target.closest('#so-neu')) { oeffnen(null); return; }
    const b = e.target.closest('[data-so]'), k = e.target.closest('[data-so-id]');
    if (!b || !k) return;
    const z = d.sonder.find((x) => x.id === k.dataset.soId);
    if (!z) return;
    const a = b.dataset.so;
    if (a === 'editor') { if (!S.oeffnen(z.id)) { await W.loadOffers(); S.oeffnen(z.id); } return; }
    if (a === 'einstellungen') { oeffnen(z); return; }
    if (a === 'beenden' || a === 'fortsetzen') {
      const ende = a === 'beenden';
      if (ende && !(await confirmBox('Sonderangebot beenden?', `„${esc(z.name)}“ ist danach sofort für keinen Kunden mehr sichtbar. Es bleibt gespeichert und lässt sich fortsetzen.`, 'Beenden', true))) return;
      await speichern({ id: z.id, name: z.name, gruppen: z.gruppen, gueltig: z.gueltig, beendet: ende }, ende ? `„${z.name}“ beendet.` : `„${z.name}“ läuft weiter.`);
      return;
    }
    if (a === 'loeschen') {
      if (!(await confirmBox('Sonderangebot löschen?', `„${esc(z.name)}“ wird mit seinen Preisen gelöscht${z.status === 'laeuft' ? ' – <strong>Kunden sehen es sofort nicht mehr</strong>' : ''}. Das lässt sich nicht rückgängig machen.`, 'Löschen', true))) return;
      try {
        const r = await api('sonderangebot_loeschen', { body: { id: z.id, rev: d.rev } });
        S.uebernehmen(r);
        toast(`„${z.name}“ gelöscht.`);
      } catch (ex) { toast(ex.message, 7000); }
      await render();
    }
  });

  /* ---------- Fenster „Sonderangebot“: Name, Gültigkeit (Kippschalter Zeitraum ↔ KW), Kundengruppen ---------- */
  function oeffnen(z) {
    if (!darf()) return;
    const heute = iso(new Date());
    const g = (z && z.gueltig) || {};
    const k = g.modus === 'kw' ? { kw: g.kw, jahr: g.jahr } : kwVon(plus(7));
    ed = { id: z ? z.id : '', name: z ? z.name : '', modus: g.modus === 'kw' ? 'kw' : 'zeitraum', von: g.von || (z ? z.von : heute), bis: g.bis || (z ? z.bis : plus(6)),
           kw: k.kw, jahr: k.jahr, gruppen: new Set(z ? z.gruppen : []), gq: '' };
    fenster();
    dlg.showModal();
    $('#so-name').focus();
  }
  function fenster(fehler = '') {
    const kw = ed.modus === 'kw';
    const fremd = [...ed.gruppen].filter((nr) => !d.gruppen.some((g) => g.nr === nr));
    const liste = [...d.gruppen, ...fremd.map((nr) => ({ nr, name: 'nicht mehr vorhanden', fremd: true }))];
    body.innerHTML = `
      <div class="dlg-head"><div><h2 id="so-title">${ed.id ? 'Sonderangebot ändern' : 'Neues Sonderangebot'}</h2><p>Gilt für ganze Kundengruppen – zusätzlich zu deren Wochen- bzw. Kundenangebot. Artikel und Preise danach im Editor.</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body form-grid two">
        <label class="fld span2"><span>Name</span><input id="so-name" name="name" maxlength="80" required autocomplete="off" placeholder="z. B. Grillaktion Gastronomie" value="${esc(ed.name)}"></label>
        <div class="fld span2"><span id="so-gl">Gültig</span>
          <div class="so-kipp" role="group" aria-labelledby="so-gl">
            <button type="button" class="so-kl${kw ? '' : ' an'}" data-modus="zeitraum">Zeitraum</button>
            <button type="button" role="switch" class="so-schalter" id="so-modus" aria-checked="${kw}" aria-label="Kalenderwoche statt Zeitraum"><i></i></button>
            <button type="button" class="so-kl${kw ? ' an' : ''}" data-modus="kw">Kalenderwoche</button>
          </div></div>
        ${kw ? `<label class="fld"><span>Kalenderwoche</span><input name="kw" type="number" min="1" max="53" inputmode="numeric" value="${esc(ed.kw)}" required></label>
          <label class="fld"><span>Jahr</span><input name="jahr" type="number" min="2000" max="2100" inputmode="numeric" value="${esc(ed.jahr)}" required></label>`
          : `<label class="fld"><span>Von</span><input name="von" type="date" value="${esc(ed.von)}" required></label>
          <label class="fld"><span>Bis (einschließlich)</span><input name="bis" type="date" value="${esc(ed.bis)}" required></label>`}
        <p class="hint span2 so-tage" id="so-tage" aria-live="polite"></p>
        <div class="span2 so-feld so-gw"><span class="so-lbl">Kundengruppen <small id="so-gn"></small></span>
          ${d.gruppen.length || fremd.length ? `<div class="search">${icon('search')}<input id="so-gq" type="search" autocomplete="off" placeholder="Gruppe finden: Nummer, Bezeichnung …" aria-label="Kundengruppen suchen" value="${esc(ed.gq)}"></div>
          <ul class="ofg-list so-glist">${liste.map((g) => `<li data-hay="${esc(SU.heu(g.nr, g.name))}"><label class="check"><input type="checkbox" value="${esc(g.nr)}"${ed.gruppen.has(g.nr) ? ' checked' : ''}> <span class="muted">${esc(g.nr)}</span> ${esc(g.name)}${typeof g.kunden === 'number' ? ` <small class="muted">· ${plural(g.kunden, 'Kunde', 'Kunden')}</small>` : ''}</label></li>`).join('')}</ul>`
            : '<p class="hint">Noch keine Kundengruppen angelegt – bitte zuerst unter Stammdaten → Kundengruppen importieren.</p>'}
        </div>
        <p class="form-err span2" id="so-err" role="alert">${esc(fehler)}</p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary" id="so-ok">${icon('check')}${ed.id ? 'Speichern' : 'Anlegen und Artikel wählen'}</button></div>`;
    gFilter(); tage();
  }
  function gFilter() {
    const toks = SU.woerter(ed.gq);
    for (const li of $$('#sonder-body .so-glist li')) li.hidden = !SU.passt(toks, li.dataset.hay);
    const n = $('#so-gn');
    if (n) {
      const k = d.kundenZahl ? [...ed.gruppen].reduce((s, nr) => s + ((d.gruppen.find((g) => g.nr === nr) || {}).kunden || 0), 0) : null;
      n.textContent = `${plural(ed.gruppen.size, 'Gruppe', 'Gruppen')} gewählt${k !== null && ed.gruppen.size ? ` · ${plural(k, 'Kunde', 'Kunden')}` : ''}`;
    }
  }
  /* Tage der Gültigkeit unter den Feldern (wie der Server rechnet: KW = Montag bis Sonntag) */
  function zeitraum() {
    if (ed.modus === 'kw') { const k = +ed.kw, j = +ed.jahr; if (!kwGibt(k, j) || j < 2000 || j > 2100) return null; const r = kwTage(k, j); return { von: r.start, bis: r.end }; }
    return ed.von && ed.bis ? { von: ed.von, bis: ed.bis } : null;
  }
  function tage() {
    const el = $('#so-tage');
    if (!el) return;
    const z = zeitraum(), heute = iso(new Date());
    if (!z) { el.textContent = ed.modus === 'kw' ? `Die KW ${ed.kw || '?'}/${ed.jahr || '?'} gibt es nicht.` : 'Bitte Beginn und Ende wählen.'; el.className = 'hint span2 so-tage warn'; return; }
    if (z.von > z.bis) { el.textContent = 'Das Ende liegt vor dem Beginn.'; el.className = 'hint span2 so-tage warn'; return; }
    const n = Math.round((new Date(z.bis + 'T12:00:00') - new Date(z.von + 'T12:00:00')) / 864e5) + 1;
    const st = heute < z.von ? 'beginnt später' : heute > z.bis ? 'liegt in der Vergangenheit' : 'läuft ab sofort';
    el.textContent = `${wt(z.von)} ${dmy(z.von)} bis ${wt(z.bis)} ${dmy(z.bis)} · ${plural(n, 'Tag', 'Tage')} · ${st}`;
    el.className = 'hint span2 so-tage' + (heute > z.bis ? ' warn' : '');
  }
  function felderLesen() {
    const f = body.elements;
    ed.name = f.name.value;
    if (ed.modus === 'kw') { ed.kw = f.kw.value; ed.jahr = f.jahr.value; } else { ed.von = f.von.value; ed.bis = f.bis.value; }
  }
  function modus(m) {
    if (m === ed.modus) return;
    felderLesen();
    if (m === 'kw') { const k = kwVon(ed.von || iso(new Date())); ed.kw = k.kw; ed.jahr = k.jahr; }   // KW des bisherigen Beginns
    else { const z = zeitraum(); if (z) { ed.von = z.von; ed.bis = z.bis; } }                        // Montag bis Sonntag der KW
    ed.modus = m;
    fenster();
    $('#so-modus').focus();
  }
  body.addEventListener('click', (e) => {
    if (e.target.closest('[data-close]')) { dlg.close(); return; }
    if (e.target.closest('#so-modus')) { modus(ed.modus === 'kw' ? 'zeitraum' : 'kw'); return; }
    const m = e.target.closest('[data-modus]');
    if (m) modus(m.dataset.modus);
  });
  body.addEventListener('input', (e) => {
    if (e.target.id === 'so-gq') { ed.gq = e.target.value; gFilter(); return; }
    if (['von', 'bis', 'kw', 'jahr'].includes(e.target.name)) { felderLesen(); tage(); }
  });
  body.addEventListener('change', (e) => {
    if (e.target.closest('.so-glist') && e.target.type === 'checkbox') { if (e.target.checked) ed.gruppen.add(e.target.value); else ed.gruppen.delete(e.target.value); gFilter(); }
  });
  body.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (busy) return;
    felderLesen();
    const gueltig = ed.modus === 'kw' ? { modus: 'kw', kw: Number(ed.kw), jahr: Number(ed.jahr) } : { modus: 'zeitraum', von: ed.von, bis: ed.bis };
    if (!ed.gruppen.size) { $('#so-err').textContent = 'Bitte mindestens eine Kundengruppe wählen – ein Sonderangebot gilt immer für Kundengruppen.'; return; }
    const neu = !ed.id;
    const gruppen = [...ed.gruppen].sort((x, y) => x.localeCompare(y, 'de', { numeric: true }));
    const r = await speichern({ id: ed.id, name: ed.name.trim(), gruppen, gueltig }, null, (msg) => { $('#so-err').textContent = msg; });   // „beendet“ bleibt, wie es ist
    if (!r) return;
    dlg.close();
    if (neu) {
      toast(`„${ed.name.trim()}“ angelegt – jetzt Artikel hinzufügen oder „Aus anderem Angebot“ übernehmen.`, 6000);
      S.oeffnen(r.id);
    }
  });
  /* Speichern über den Server (Prüfung dort); danach Angebotsliste im Editor und diese Liste neu */
  async function speichern(b, meldung, fehler) {
    busy = true;
    const ok = $('#so-ok'); if (ok) ok.disabled = true;
    try {
      const r = await api('sonderangebot_save', { body: { ...b, rev: d.rev } });
      S.uebernehmen(r);
      if (meldung) toast(meldung);
      await laden(); liste();
      return r;
    } catch (ex) {
      if (fehler) fehler(ex.message); else toast(ex.message, 7000);
      if (ex.status === 409) { try { await laden(); liste(); } catch { /* Hinweis bleibt */ } }
      return null;
    } finally { busy = false; if (ok) ok.disabled = false; }
  }

  W.views.sonder = render;
  /* Knopf „Gültigkeit und Gruppen“ im Kopf des Editors (admin.js) */
  S.bearbeiten = async (id) => {
    W.setView('sonder');
    try { if (!d) await laden(); } catch (e) { toast(e.message); return; }
    const z = d.sonder.find((x) => x.id === id);
    if (z) oeffnen(z);
  };
})();
