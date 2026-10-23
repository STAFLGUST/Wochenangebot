/* STAFL-Plattform · HR im Eingabebereich der Verwaltung
   - Verwaltung → Mitarbeiter: HR-Angaben je Mitarbeiter (Abteilung, Position, Arbeitstage, im Urlaubsplan, Urlaubsanspruch
     und Übertrag je Jahr) – im Dialog des Mitarbeiters (Administratoren) bzw. als eigene Liste (Personalstelle ohne
     Administratorrechte). Mitarbeiter = Nutzer der Plattform; auch Kollegen ohne Anmeldung sind Mitarbeiter.
   - Verwaltung → Urlaub: Urlaubssperren und Ferien.
   - Verwaltung → Import: Leser „Urlaubsplanung (Excel)“ und „Abwesenheiten aus der Zeiterfassung“ (window.WA.importLeser).
   Alle Rechte prüft der Server (hr.verwalten, GR-103); hier ist nur die Anzeige. Wird von admin/index.html nach
   admin.js, admin-verwaltung.js und admin-import.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  if (!W) return;
  const { $, $$, api, esc, icon, toast, may } = W;
  const WT = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  const zahl = (n) => (Math.round(Number(n || 0) * 2) / 2).toLocaleString('de-DE', { maximumFractionDigits: 1 });
  let daten = null;                      // Antwort von mitarbeiter_hr (aktuelles Jahr)
  const JAHR = new Date().getFullYear();

  async function laden() {
    if (!may('hr.verwalten')) { daten = null; return null; }
    daten = await api('mitarbeiter_hr&jahr=' + JAHR);
    return daten;
  }
  const person = (uid) => (daten ? daten.personen.find((p) => p.nutzer === uid) : null);

  /* ---------- Spalten der Mitarbeiterliste (Administratoren) ---------- */
  function zelle(uid) {
    const p = person(uid);
    if (!p) return { abteilung: '', urlaub: '' };
    return {
      abteilung: esc(p.abteilung || ''),
      urlaub: p.aktiv ? `<span title="Resturlaub ${JAHR}">${esc(zahl(p.konto.rest))} Tage</span>` : '<span class="muted" title="nicht im Urlaubsplan">–</span>',
    };
  }

  /* ---------- HR-Teil im Dialog ---------- */
  function formular(uid) {
    if (!may('hr.verwalten')) return '';
    const p = uid ? person(uid) : null;
    const abt = [...new Set((daten ? daten.personen : []).map((x) => x.abteilung).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'de'));
    const at = p ? p.arbeitstage : [1, 2, 3, 4, 5];
    const jv = (p && p.jahre[String(JAHR)]) || {};
    const maxPos = Math.max(0, ...(daten ? daten.personen.map((x) => x.pos || 0) : [0]));
    return `<fieldset class="span2 hr-teil" id="hr-teil" data-uid="${esc(uid || '')}"><legend>Urlaubsverwaltung</legend>
      <div class="form-grid two">
        <label class="fld span2"><span>Abteilung</span><input name="hr_abteilung" value="${esc(p ? p.abteilung : '')}" maxlength="40" list="hr-abteilungen" autocomplete="off"></label>
        <label class="fld"><span>Personalnummer <small class="muted">(Zeiterfassung)</small></span><input name="hr_personalnummer" value="${esc(p ? p.personalnummer || '' : '')}" maxlength="20" autocomplete="off" inputmode="numeric"></label>
        <label class="fld"><span>Position <small class="muted">(Reihenfolge im Plan)</small></span><input name="hr_pos" type="number" min="0" max="9999" value="${esc(p ? p.pos || '' : maxPos + 1)}"></label>
        <div class="span2 hr-tage-feld"><span class="hr-lbl">Arbeitstage</span><div class="hr-tage">${WT.map((w, i) => `<label class="check"><input type="checkbox" name="hr_tag" value="${i + 1}"${at.includes(i + 1) ? ' checked' : ''}> ${w}</label>`).join('')}</div></div>
        <label class="fld"><span>Urlaubsanspruch ${JAHR}</span><input name="hr_anspruch" type="number" min="0" max="100" step="0.5" value="${esc(jv.anspruch ?? (p && p.konto.anspruch ? p.konto.anspruch : ''))}"></label>
        <label class="fld"><span>Übertrag aus ${JAHR - 1}</span><input name="hr_uebertrag" type="number" min="-100" max="100" step="0.5" value="${esc(jv.uebertrag ?? '')}" placeholder="${p ? 'automatisch (' + esc(zahl(p.konto.uebertrag)) + ')' : 'automatisch'}"></label>
        <label class="check span2"><input type="checkbox" name="hr_aktiv"${!p || p.aktiv ? ' checked' : ''}> im Urlaubsplan (Kalender, Export für den Steuerberater)</label>
      </div>
      <datalist id="hr-abteilungen">${abt.map((a) => `<option value="${esc(a)}">`).join('')}</datalist>
      ${p && p.aktiv ? `<p class="hint" style="margin:0">Urlaub ${JAHR}: ${esc(zahl(p.konto.rest))} Tage Rest · ${esc(zahl(p.konto.genommen))} genommen · ${esc(zahl(p.konto.geplant))} geplant${p.konto.verfaellt > 0 ? ` · ${esc(zahl(p.konto.verfaellt))} Tage Übertrag verfallen nach dem 31.03.` : ''}</p>` : ''}
    </fieldset>`;
  }

  /* HR-Angaben aus dem Formular speichern (nach dem Speichern des Mitarbeiters, mit dessen Kennung) */
  async function speichern(uid, form) {
    const teil = form.querySelector('#hr-teil');
    if (!teil || !may('hr.verwalten')) return;
    if (!daten) await laden();
    const wert = (n) => form.querySelector(`[name="${n}"]`).value;
    const body = { nutzer: uid, rev: daten.rev, abteilung: wert('hr_abteilung'), personalnummer: wert('hr_personalnummer').trim(), pos: Number(wert('hr_pos') || 0),
      arbeitstage: [...form.querySelectorAll('[name="hr_tag"]:checked')].map((x) => Number(x.value)),
      aktiv: form.querySelector('[name="hr_aktiv"]').checked, jahr: JAHR, anspruch: wert('hr_anspruch'), uebertrag: wert('hr_uebertrag') };
    let r;
    try { r = await api('mitarbeiter_hr_save', { body }); }
    catch (ex) { if (ex.status !== 409) throw ex; await laden(); r = await api('mitarbeiter_hr_save', { body: { ...body, rev: daten.rev } }); }
    daten.rev = r.rev;
    if (r.person) { const i = daten.personen.findIndex((p) => p.nutzer === uid); if (i >= 0) daten.personen[i] = r.person; else daten.personen.push(r.person); }
  }

  /* Hinweis: Einträge der Urlaubsliste ohne Mitarbeiter (Altbestand) übernehmen */
  function altbestand() {
    if (!daten || !may('hr.verwalten')) return '';
    const alt = daten.personen.filter((p) => p.altbestand);
    if (!alt.length) return '';
    return `<div class="gcard hr-alt" id="hr-alt"><p><strong>${alt.length === 1 ? '1 Eintrag' : alt.length + ' Einträge'} der Urlaubsliste ohne Mitarbeiter:</strong>
      ${esc(alt.slice(0, 8).map((p) => `${p.vorname} ${p.nachname}`.trim()).join(', '))}${alt.length > 8 ? ' …' : ''}.
      Beim Übernehmen wird jeder Eintrag dem gleichnamigen Mitarbeiter zugeordnet oder als Mitarbeiter ohne Anmeldung angelegt – Urlaub und Abwesenheiten bleiben erhalten.</p>
      <button type="button" class="btn primary" data-hr-alt>${icon('check', 'sm')}In Mitarbeiter übernehmen</button></div>`;
  }
  async function altbestandUebernehmen(btn, nachher) {
    btn.disabled = true;
    try { const r = await api('hr_personal_uebernehmen', { body: {} }); toast(r.anzahl === 1 ? '1 Eintrag übernommen.' : `${r.anzahl} Einträge übernommen.`); await nachher(); }
    catch (ex) { toast(ex.message, 6000); btn.disabled = false; }
  }

  /* ---------- Personalstelle ohne Administratorrechte: nur HR-Angaben ---------- */
  let hrDlg = null;
  async function renderNurHr(host) {
    host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Mitarbeiter werden geladen …</div>';
    try { await laden(); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    const ps = daten.personen.filter((p) => !p.altbestand);
    host.innerHTML = `<p class="hint hr-nurhr">${ps.length} Mitarbeiter · Abteilung, Arbeitstage und Urlaubsanspruch. Anmeldung, Rollen und Rechte verwaltet ein Administrator.</p>
      ${altbestand()}
      <div class="gcard"><table class="etab utab"><thead><tr><th>Name</th><th>Abteilung</th><th>Arbeitstage</th><th class="num">Anspruch</th><th class="num">Übertrag</th><th class="num">Rest ${JAHR}</th><th class="u-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>
      ${ps.map((p) => `<tr data-hr-uid="${esc(p.nutzer)}" tabindex="0" class="${p.aktiv ? '' : 'inactive'}"><td class="u-name"><div class="nm">${esc(`${p.vorname} ${p.nachname}`.trim())}</div><div class="sub">${p.zugang ? esc(p.username) : 'ohne Anmeldung'}${p.personalnummer ? ' · Nr. ' + esc(p.personalnummer) : ''}</div></td>
        <td>${esc(p.abteilung)}</td><td>${esc(p.arbeitstage.map((w) => WT[w - 1]).join(' '))}</td><td class="num">${esc(zahl(p.konto.anspruch))}</td>
        <td class="num">${esc(zahl(p.konto.uebertrag))}</td><td class="num"><strong>${p.aktiv ? esc(zahl(p.konto.rest)) : '–'}</strong></td>
        <td class="u-act"><button type="button" class="btn sm">Bearbeiten</button></td></tr>`).join('')}</tbody></table></div>`;
  }
  function nurHrDialog(uid, host) {
    if (!hrDlg) {
      hrDlg = document.createElement('dialog');
      hrDlg.className = 'modal'; hrDlg.id = 'dlg-hr-person'; hrDlg.setAttribute('aria-labelledby', 'hrp-title');
      hrDlg.innerHTML = '<form class="dlg" id="hr-person-body" autocomplete="off"></form>';
      document.body.append(hrDlg);
      hrDlg.addEventListener('click', (e) => { if (e.target.closest('[data-close]')) hrDlg.close(); });
      hrDlg.querySelector('form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const f = e.target, err = f.querySelector('.form-err');
        err.textContent = '';
        try { await speichern(f.dataset.uid, f); hrDlg.close(); toast('Gespeichert.'); renderNurHr(host); } catch (ex) { err.textContent = ex.message; }
      });
    }
    const p = person(uid);
    const f = hrDlg.querySelector('form');
    f.dataset.uid = uid;
    f.innerHTML = `<div class="dlg-head"><div><h2 id="hrp-title">${esc(`${p.vorname} ${p.nachname}`.trim())}</h2><p>${p.zugang ? 'Mitarbeiter mit Anmeldung' : 'Mitarbeiter ohne Anmeldung'}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Abbrechen">${icon('x')}</button></div>
      <div class="dlg-body form-grid two">${formular(uid)}<p class="form-err span2" role="alert"></p></div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary">Speichern</button></div>`;
    hrDlg.showModal();
  }

  /* ---------- Verwaltung → Urlaub: Urlaubssperren und Ferien ---------- */
  const zeile = (z) => `<div class="hr-zr"><input type="date" value="${esc(z.von || '')}" aria-label="Von"><input type="date" value="${esc(z.bis || '')}" aria-label="Bis">
    <input type="text" value="${esc(z.text || '')}" maxlength="80" placeholder="Bezeichnung" aria-label="Bezeichnung"><button type="button" class="btn icon ghost" data-weg aria-label="Entfernen">${icon('x')}</button></div>`;
  async function renderUrlaub() {
    const host = $('#view-urlaub');
    host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Wird geladen …</div>';
    try { await laden(); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    host.innerHTML = `<form class="gcard hr-einst" id="hr-einst">
      <h3 class="sec-h">Urlaubssperren</h3><p class="hint">In diesen Zeiträumen können Mitarbeiter keinen Urlaub beantragen; die Personalstelle kann weiter eintragen.</p>
      <div id="hr-sperren">${daten.sperren.map(zeile).join('')}</div><button type="button" class="btn sm" data-plus="hr-sperren">${icon('plus', 'sm')}Sperre</button>
      <h3 class="sec-h">Ferien</h3><p class="hint">Nur zur Anzeige im Kalender und im Excel-Export (grün).</p>
      <div id="hr-ferien">${daten.ferien.map(zeile).join('')}</div><button type="button" class="btn sm" data-plus="hr-ferien">${icon('plus', 'sm')}Ferien</button>
      <p class="hint">Mitarbeiter, Abteilungen, Arbeitstage und Urlaubsanspruch: Verwaltung → Mitarbeiter. Urlaub und Krankheit aus der Zeiterfassung: Verwaltung → Import → „Abwesenheiten aus der Zeiterfassung“.</p>
      <p class="form-err" id="hr-einst-err" role="alert"></p>
      <div class="sec-foot"><button type="submit" class="btn primary">${icon('check', 'sm')}Speichern</button></div></form>`;
  }
  document.addEventListener('click', (e) => {
    const plus = e.target.closest('#hr-einst [data-plus]');
    if (plus) $('#' + plus.dataset.plus).insertAdjacentHTML('beforeend', zeile({}));
    const weg = e.target.closest('#hr-einst [data-weg]');
    if (weg) weg.parentElement.remove();
    const alt = e.target.closest('[data-hr-alt]');
    if (alt) altbestandUebernehmen(alt, async () => { await laden(); if (W.views.users) W.views.users(); });
    const tr = e.target.closest('tr[data-hr-uid]');
    if (tr) nurHrDialog(tr.dataset.hrUid, $('#view-users'));
  });
  document.addEventListener('submit', async (e) => {
    if (e.target.id !== 'hr-einst') return;
    e.preventDefault();
    const liste = (id) => $$('#' + id + ' .hr-zr').map((z) => { const i = $$('input', z); return { von: i[0].value, bis: i[1].value, text: i[2].value }; });
    try {
      const r = await api('hr_einstellungen_save', { body: { sperren: liste('hr-sperren'), ferien: liste('hr-ferien') } });
      daten.sperren = r.sperren; daten.ferien = r.ferien;
      toast('Urlaubssperren und Ferien gespeichert.');
      renderUrlaub();
    } catch (ex) { $('#hr-einst-err').textContent = ex.message; }
  });
  W.views.urlaub = renderUrlaub;

  /* ---------- Importzentrale: Leser „Urlaubsplanung (Excel)“ ---------- */
  W.importLeser = W.importLeser || {};
  W.importLeser.urlaubsplanung = {
    async lesen(files) {
      const f = files[0];
      const blaetter = await window.OfferCore.xlsxReadWorkbook(await f.arrayBuffer());
      // nur die Zellen, die der Server braucht: Zeilen bis 300, Spalten bis 40
      const daten_ = { blaetter: blaetter.map((b) => ({ name: b.name, grid: b.grid.slice(0, 300).map((z) => Array.from({ length: Math.min(z.length, 40) }, (_, i) => z[i] ?? null)) })) };
      return { daten: daten_, zeilen: blaetter.length, fehler: [], hinweise: [] };
    },
    nachher() { daten = null; },
  };

  /* ---------- Importzentrale: Leser „Abwesenheiten aus der Zeiterfassung“ (Abwesenheitsbericht) ---------- */
  W.importLeser.zeiterfassung = {
    async lesen(files) {
      const f = files[0];
      const blaetter = await window.OfferCore.xlsxReadWorkbook(await f.arrayBuffer());
      const b = blaetter[0];
      if (!b) return { daten: { blaetter: [] }, zeilen: 0, fehler: [{ datei: f.name, text: 'Die Datei enthält kein Tabellenblatt.' }], hinweise: [] };
      // ein Blatt, Zeilen bis 5000, Spalten bis 15 (Datumswerte als Excel-Seriennummer – der Server rechnet um)
      const grid = b.grid.slice(0, 5000).map((z) => Array.from({ length: Math.min(z.length, 15) }, (_, i) => z[i] ?? null));
      const hinweise = b.grid.length > 5000 ? [{ stufe: 'warn', text: 'Nur die ersten 5000 Zeilen werden gelesen.' }] : [];
      return { daten: { blaetter: [{ name: b.name, grid }] }, zeilen: grid.length, fehler: [], hinweise };
    },
    nachher() { daten = null; },
  };

  W.hr = { laden, zelle, formular, speichern, altbestand, renderNurHr, get daten() { return daten; } };
})();
