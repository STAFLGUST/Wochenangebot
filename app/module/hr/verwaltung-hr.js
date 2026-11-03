/* STAFL-Plattform · HR im Eingabebereich der Verwaltung
   - Verwaltung → Mitarbeiter: HR-Angaben je Mitarbeiter (Abteilung, Position, Arbeitstage, im Urlaubsplan, Urlaubsanspruch
     und Übertrag je Jahr, ob der Resturlaub verfällt) – im Dialog des Mitarbeiters (Administratoren) bzw. als eigene Liste (Personalstelle ohne
     Administratorrechte). Mitarbeiter = Nutzer der Plattform; auch Kollegen ohne Anmeldung sind Mitarbeiter.
   - Verwaltung → Urlaub: Schalter „Urlaubsanträge über die Plattform“, Urlaubssperren (eigene und automatisch aus den
     Urlaubsregeln), Ferien, Verfallstag des Resturlaubs, Text der Urlaubsregeln (steht beim Urlaubsantrag), E-Mails
     (Erinnerung „Resturlaub verfällt“, Monatsübersicht an die Mitarbeiter, Übersicht an den Steuerberater, Testmodus).
   - Verwaltung → Import: Leser „Abwesenheiten aus der Zeiterfassung“ (window.WA.importLeser).
   Alle Rechte prüft der Server (hr.verwalten, GR-103); hier ist nur die Anzeige. Wird von admin/index.html nach
   admin.js, admin-verwaltung.js und admin-import.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  if (!W) return;
  const { $, $$, api, esc, icon, toast, may, confirmBox } = W;
  const WT = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  const zahl = (n) => window.STAFL_FORMAT.zahl(Math.round(Number(n || 0) * 2) / 2, 0, 1);   // halbe Tage, echtes Minus wie überall
  let daten = null;                      // Antwort von mitarbeiter_hr (aktuelles Jahr)
  // Kennzeichen „Resturlaub verfällt nicht“ (Verfall je Mitarbeiter abgeschaltet) in den Listen
  const kVerfall = '<small class="hr-kein-verfall" title="Resturlaub aus dem Vorjahr verfällt nicht">kein Verfall</small>';
  const JAHR = new Date().getFullYear();
  const datumDe = (iso) => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || ''); return m ? `${m[3]}.${m[2]}.${m[1]}` : ''; };
  const tagMonat = (mmtt) => { const m = /^(\d{2})-(\d{2})$/.exec(mmtt || ''); return m ? `${m[2]}.${m[1]}.` : '31.03.'; };   // Verfallstag „MM-TT“ → „TT.MM.“
  // Übergangsregel (hr-einstellungen.verfallAb): erstes Jahr mit Verfall; davor verfällt nichts
  const verfallText = (d) => (d && d.verfallAb ? `erstmals am ${tagMonat(d.uebertragBis)}${d.verfallAb}` : `jedes Jahr am ${tagMonat(d && d.uebertragBis)}`);

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
      urlaub: p.aktiv ? `<span title="Resturlaub ${JAHR}">${esc(zahl(p.konto.rest))} Tage</span>${p.verfall === false ? kVerfall : ''}` : '<span class="muted" title="nicht im Urlaubsplan">–</span>',
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
    // eigene Person: Urlaubsangaben ändert eine andere Person der Personalstelle (Vier-Augen-Prinzip, der Server prüft das)
    const eigen = !!(uid && W.me && W.me.id === uid);
    const aus = eigen ? ' disabled' : '';
    return `<fieldset class="span2 hr-teil${eigen ? ' hr-eigen' : ''}" id="hr-teil" data-uid="${esc(uid || '')}"><legend>Urlaubsverwaltung</legend>
      ${eigen ? `<p class="hr-eigen-hinweis">${icon('lock', 'sm')}<span>Ihre eigenen Urlaubsangaben (Anspruch, Übertrag, Verfall, Arbeitstage, Urlaubsplan, Personalnummer) ändert eine andere Person der Personalstelle (Vier-Augen-Prinzip). Abteilung und Position können Sie selbst ändern.</span></p>` : ''}
      <div class="form-grid two">
        <label class="fld span2"><span>Abteilung</span><input name="hr_abteilung" value="${esc(p ? p.abteilung : '')}" maxlength="40" list="hr-abteilungen" autocomplete="off"></label>
        <label class="fld"><span>Personalnummer <small class="muted">(Zeiterfassung)</small></span><input name="hr_personalnummer" value="${esc(p ? p.personalnummer || '' : '')}" maxlength="20" autocomplete="off" inputmode="numeric"${aus}></label>
        <label class="fld"><span>Position <small class="muted">(Reihenfolge im Plan)</small></span><input name="hr_pos" type="number" min="0" max="9999" value="${esc(p ? p.pos || '' : maxPos + 1)}"></label>
        <div class="span2 hr-tage-feld"><span class="hr-lbl">Arbeitstage</span><div class="hr-tage">${WT.map((w, i) => `<label class="check"><input type="checkbox" name="hr_tag" value="${i + 1}"${at.includes(i + 1) ? ' checked' : ''}${aus}> ${w}</label>`).join('')}</div></div>
        <label class="fld"><span>Urlaubsanspruch ${JAHR}</span><input name="hr_anspruch" type="number" min="0" max="100" step="0.5" value="${esc(jv.anspruch ?? (p && p.konto.anspruch ? p.konto.anspruch : ''))}"${aus}></label>
        <label class="fld"><span>Übertrag aus ${JAHR - 1}</span><input name="hr_uebertrag" type="number" min="-100" max="100" step="0.5" value="${esc(jv.uebertrag ?? '')}" placeholder="${p ? 'automatisch (' + esc(zahl(p.konto.uebertrag)) + ')' : 'automatisch'}"${aus}></label>
        <label class="check span2 hr-verfall-check"><input type="checkbox" name="hr_verfall"${!p || p.verfall !== false ? ' checked' : ''}${aus}> <span>Resturlaub aus dem Vorjahr verfällt am ${esc(tagMonat(daten && daten.uebertragBis))}${daten && daten.verfallAb > JAHR ? ` (erstmals ${esc(tagMonat(daten.uebertragBis))}${daten.verfallAb})` : ''}<small class="muted">Ohne Haken bleibt der Übertrag das ganze Jahr erhalten.${daten && daten.verfallAb > JAHR ? ` Bis ${daten.verfallAb - 1} verfällt bei niemandem etwas (Verwaltung → Urlaub).` : ''}</small></span></label>
        <label class="check span2"><input type="checkbox" name="hr_aktiv"${!p || p.aktiv ? ' checked' : ''}${aus}> im Urlaubsplan (Kalender, Export für den Steuerberater)</label>
      </div>
      <datalist id="hr-abteilungen">${abt.map((a) => `<option value="${esc(a)}">`).join('')}</datalist>
      ${p && p.aktiv ? `<p class="hint" style="margin:0">Urlaub ${JAHR}: ${esc(zahl(p.konto.rest))} Tage Rest · ${esc(zahl(p.konto.genommen))} genommen · ${esc(zahl(p.konto.geplant))} geplant${p.konto.verfaellt > 0 ? ` · ${esc(zahl(p.konto.verfaellt))} Tage Übertrag verfallen nach dem ${esc(tagMonat((p.konto.frist || '').slice(5)))}` : ''}${p.gleitKonto && p.gleitKonto.aktiv ? ` · Gleittage: ${esc(zahl(p.gleitKonto.rest))} Rest (gewähren in HR → Übersicht)` : ''}</p>` : ''}
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
      aktiv: form.querySelector('[name="hr_aktiv"]').checked, verfall: form.querySelector('[name="hr_verfall"]').checked, jahr: JAHR, anspruch: wert('hr_anspruch'), uebertrag: wert('hr_uebertrag') };
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
    return `<div class="gcard hr-alt" id="hr-alt"><p><strong>${alt.length === 1 ? '1 ehemaliger Mitarbeiter' : alt.length + ' ehemalige Mitarbeiter'} (nicht zugeordnet):</strong>
      ${esc(alt.slice(0, 8).map((p) => `${p.vorname} ${p.nachname}`.trim()).join(', '))}${alt.length > 8 ? ' …' : ''}.
      Sie zählen nicht mehr im Urlaubsplan (Kalender, Übersicht); ihre bisherigen Einträge bleiben erhalten.
      Arbeitet jemand davon noch hier, <strong>einzeln zuordnen</strong> – Personalnummer und Urlaub gehen dann auf den Mitarbeiter über.</p>
      <div class="hr-alt-knoepfe"><button type="button" class="btn" data-hr-alt>${icon('check', 'sm')}Gleichnamige zuordnen</button>
      <button type="button" class="btn primary" data-hr-alt-einzeln>Einzeln zuordnen …</button></div></div>`;
  }

  /* Einzeln zuordnen: jeden Eintrag ohne Mitarbeiter einem gewählten Mitarbeiter zuordnen – auch bei anderem Namen;
     hat der Mitarbeiter schon HR-Angaben, führt der Server beide zusammen (hr_altbestand_zuordnen) */
  let altDlg = null;
  const nk = (p) => `${p.vorname} ${p.nachname}`.trim();
  function vorschlag(e, ps) {
    // gleicher Nachname, eindeutig – sonst keine Vorauswahl
    const t = ps.filter((p) => p.nachname && e.nachname && p.nachname.toLocaleLowerCase('de-DE') === e.nachname.toLocaleLowerCase('de-DE'));
    return t.length === 1 ? t[0].nutzer : '';
  }
  function altDialogInhalt() {
    const alt = daten.personen.filter((p) => p.altbestand);
    const ps = daten.personen.filter((p) => !p.altbestand).sort((a, b) => nk(a).localeCompare(nk(b), 'de'));
    const opts = (sel) => '<option value="">– Mitarbeiter wählen –</option>' + ps.map((p) => `<option value="${esc(p.nutzer)}"${p.nutzer === sel ? ' selected' : ''}>${esc(nk(p))}${p.zugang ? ' (' + esc(p.username) + ')' : ' (ohne Anmeldung)'}</option>`).join('');
    return `<div class="dlg-head"><div><h2 id="hra-title">Ehemalige Mitarbeiter zuordnen</h2><p>Abwesenheiten, Personalnummer, Anspruch und Übertrag gehen auf den gewählten Mitarbeiter über.
        Hat er schon Angaben, gelten seine; nur leere Felder werden ergänzt.</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">${alt.length ? `<ul class="hr-alt-liste">${alt.map((e) => `<li data-eintrag="${esc(e.id)}">
          <div class="nm"><strong>${esc(nk(e))}</strong><span class="muted">${e.personalnummer ? 'Nr. ' + esc(e.personalnummer) : 'ohne Personalnummer'}${e.abteilung ? ' · ' + esc(e.abteilung) : ''}</span></div>
          <label class="fld"><span class="sr-only">Mitarbeiter für ${esc(nk(e))}</span><select>${opts(vorschlag(e, ps))}</select></label>
          <button type="button" class="btn sm primary" data-zuordnen>Zuordnen</button>
          <p class="form-err" role="alert"></p></li>`).join('')}</ul>` : '<p class="hint">Keine ehemaligen Mitarbeiter ohne Zuordnung.</p>'}</div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Fertig</button></div>`;
  }
  function altDialog(nachher) {
    if (!altDlg) {
      altDlg = document.createElement('dialog');
      altDlg.className = 'modal'; altDlg.id = 'dlg-hr-alt'; altDlg.setAttribute('aria-labelledby', 'hra-title');
      altDlg.innerHTML = '<div class="dlg"></div>';
      document.body.append(altDlg);
      altDlg.addEventListener('click', async (e) => {
        if (e.target.closest('[data-close]')) { altDlg.close(); return; }
        const b = e.target.closest('[data-zuordnen]');
        if (!b) return;
        const li = b.closest('li'), sel = li.querySelector('select'), err = li.querySelector('.form-err');
        err.textContent = '';
        if (!sel.value) { err.textContent = 'Bitte einen Mitarbeiter wählen.'; sel.focus(); return; }
        b.disabled = true;
        try {
          const r = await api('hr_altbestand_zuordnen', { body: { eintrag: li.dataset.eintrag, nutzer: sel.value, rev: daten.rev } });
          toast(`Zugeordnet: ${r.abwesenheiten === 1 ? '1 Abwesenheit' : r.abwesenheiten + ' Abwesenheiten'} übernommen${r.doppelt ? `, ${r.doppelt} doppelte storniert` : ''}.`);
          await laden();
          altDlg.querySelector('.dlg').innerHTML = altDialogInhalt();
          await nachher();
        } catch (ex) { err.textContent = ex.message; b.disabled = false; }
      });
    }
    altDlg.querySelector('.dlg').innerHTML = altDialogInhalt();
    altDlg.showModal();
  }
  async function altbestandUebernehmen(btn, nachher) {
    btn.disabled = true;
    try { const r = await api('hr_personal_uebernehmen', { body: {} }); toast(!r.anzahl ? 'Kein gleichnamiger Mitarbeiter gefunden – bitte einzeln zuordnen.' : r.anzahl === 1 ? '1 Eintrag zugeordnet.' : `${r.anzahl} Einträge zugeordnet.`, 6000); await nachher(); }
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
        <td class="num">${esc(zahl(p.konto.uebertrag))}${p.verfall === false ? kVerfall : ''}</td><td class="num"><strong>${p.aktiv ? esc(zahl(p.konto.rest)) : '—'}</strong></td>
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
    const an = daten.antraege !== false;
    host.innerHTML = `<section class="gcard hr-einst hr-antraege-karte">
      <div class="hr-antraege-kopf"><h3 class="sec-h">Urlaubsanträge über die Plattform</h3>
        <label class="rl-schalter"><input type="checkbox" role="switch" id="hr-antraege"${an ? ' checked' : ''} aria-describedby="hr-antraege-hint">
        <span class="rl-schalter-t" id="hr-antraege-t">${an ? 'Eingeschaltet' : 'Ausgeschaltet'}</span></label></div>
      <p class="hint" id="hr-antraege-hint">Ausgeschaltet sehen Mitarbeiter in der Urlaubsverwaltung kein Antragsformular mehr und können keinen Urlaub beantragen.
        Urlaubskonto, Kalender und das Eintragen durch die Personalstelle bleiben; offene Anträge können weiter entschieden oder zurückgezogen werden. Wirkt sofort.</p>
      <p class="form-err" id="hr-antraege-err" role="alert"></p></section>
    <form class="gcard hr-einst" id="hr-einst">
      <h3 class="sec-h">Urlaubssperren</h3><p class="hint">In diesen Zeiträumen können Mitarbeiter keinen Urlaub beantragen; die Personalstelle kann weiter eintragen.</p>
      <label class="check hr-regelsperren"><input type="checkbox" id="hr-regelsperren"${daten.regelSperren !== false ? ' checked' : ''}> <span>Sperren aus den Urlaubsregeln jedes Jahr automatisch
        <small class="muted">Ostergeschäft (zwei Wochen vor Karfreitag) und Weihnachtsgeschäft (letzte Novemberwoche bis 24.12.)</small></span></label>
      <ul class="hr-autosperren" id="hr-autosperren">${(daten.sperrenAuto || []).map((z) => `<li><span>${esc(z.text)} ${esc(z.von.slice(0, 4))}</span><span>${esc(datumDe(z.von))} – ${esc(datumDe(z.bis))}</span></li>`).join('')}</ul>
      <p class="hint hr-eigene-sperren">Weitere Sperren:</p>
      <div id="hr-sperren">${daten.sperren.map(zeile).join('')}</div><button type="button" class="btn sm" data-plus="hr-sperren">${icon('plus', 'sm')}Sperre</button>
      <h3 class="sec-h">Ferien</h3><p class="hint">Nur zur Anzeige im Kalender und im Excel-Export (grün).</p>
      <div id="hr-ferien">${daten.ferien.map(zeile).join('')}</div><button type="button" class="btn sm" data-plus="hr-ferien">${icon('plus', 'sm')}Ferien</button>
      <h3 class="sec-h">Resturlaub aus dem Vorjahr</h3><p class="hint">Nicht genommener Übertrag verfällt nach diesem Tag. Gilt für alle Mitarbeiter, bei denen „Resturlaub verfällt“ angehakt ist (Verwaltung → Mitarbeiter, Standard) – gespeichert werden nur Tag und Monat (der 29.02. ist nicht möglich).
        Mit „Verfällt erstmals“ gilt eine Übergangsregel: in den Jahren davor verfällt bei niemandem etwas, der ganze Rest geht ins Folgejahr.</p>
      <div class="hr-verfall-felder">
        <label class="fld hr-verfall"><span>Verfällt am</span><input type="date" id="hr-uebertrag-bis" value="${esc(`${JAHR}-${daten.uebertragBis || '03-31'}`)}" required></label>
        <label class="fld hr-verfall"><span>Verfällt erstmals</span><select id="hr-verfall-ab"><option value="">jedes Jahr</option>${[...new Set([JAHR - 1, JAHR, JAHR + 1, JAHR + 2, JAHR + 3, daten.verfallAb].filter(Boolean))].sort().map((j) => `<option value="${j}"${daten.verfallAb === j ? ' selected' : ''}>${j}</option>`).join('')}</select></label>
      </div>
      <p class="hint" id="hr-uebertrag-anzeige">Aktuell: verfällt ${esc(verfallText(daten))}${daten.verfallAb ? ` – Resturlaub aus ${daten.verfallAb - 2} bleibt ${daten.verfallAb - 1} ganz erhalten` : ''}</p>
      <h3 class="sec-h">Urlaubsregeln</h3><p class="hint">Stehen für alle Mitarbeiter beim Urlaubsantrag. Eine Zeile wie „1. Urlaubsanspruch“ wird zur Überschrift; leer = keine Regeln anzeigen.</p>
      <label class="fld hr-regeln-feld"><span class="sr-only">Text der Urlaubsregeln</span><textarea id="hr-regeln" rows="14" maxlength="6000">${esc(daten.regeln || '')}</textarea></label>
      <div class="hr-regeln-knoepfe"><button type="button" class="btn sm" id="hr-regeln-vorlage">Vorlage einsetzen</button></div>
      <p class="hint">Mitarbeiter, Abteilungen, Arbeitstage und Urlaubsanspruch: Verwaltung → Mitarbeiter. Urlaub und Krankheit aus der Zeiterfassung: Verwaltung → Import → „Abwesenheiten aus der Zeiterfassung“.</p>
      <p class="form-err" id="hr-einst-err" role="alert"></p>
      <div class="sec-foot"><button type="submit" class="btn primary">${icon('check', 'sm')}Speichern</button></div></form>
    ${mailKarte()}`;
  }

  /* ---------- Verwaltung → Urlaub: E-Mails (Server: module/hr/mail.php) ----------
     Einstellungen speichert „Speichern“ der Karte; die Knöpfe senden mit den gespeicherten Einstellungen (nach einer
     Änderung erst speichern). Der automatische Versand läuft beim ersten Aufruf der Urlaubsverwaltung ab dem Termin. */
  const MONATE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  const monatText = (ym) => (/^\d{4}-\d{2}$/.test(ym || '') ? `${MONATE[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}` : '');
  const ART = { monat: 'Monatsübersicht', erinnerung: 'Erinnerung', steuerberater: 'Steuerberater', fehlen: 'Unentschuldigt: Bitte um Erklärung' };
  function mailKarte() {
    const m = daten && daten.mail;
    if (!m) return '';
    const e = m.einst, n = m.naechste, [vor, dies] = m.monate;
    const klein = (t) => (t ? `<small class="muted">${t}</small>` : '');
    const verlauf = (m.verlauf || []).slice(0, 8).map((v) => `<li><span>${esc(W.dateTime ? W.dateTime(v.t) : v.t)}</span><span>${esc(ART[v.art] || v.art)}${v.name ? ' an ' + esc(v.name) : ''}${v.monat ? ' · ' + esc(v.monat.split('/').map(monatText).join(' und ')) : ''}${v.wie === 'automatisch' ? ' · automatisch' : ''}${v.test ? ' · Testmodus' : ''}</span>
      <span>${esc(String(v.gesendet))} gesendet${v.fehler ? ` · <b class="hr-mail-fehler">${esc(String(v.fehler))} nicht zugestellt</b>` : ''}${v.ohneAdresse ? ` · ${esc(String(v.ohneAdresse))} ohne Adresse` : ''}</span></li>`).join('');
    return `<form class="gcard hr-einst hr-mail" id="hr-mail" novalidate>
      <h3 class="sec-h">E-Mails</h3>
      ${m.postfach ? '' : '<p class="hint st-warn">Der E-Mail-Versand ist auf dem Server noch nicht eingerichtet – Einstellungen lassen sich speichern, senden geht erst danach.</p>'}
      <div class="hr-mail-block">
        <h4>Erinnerung: Resturlaub verfällt</h4>
        <p class="hint" id="hrm-erinnerung-info">${m.erinnerung ? `${m.erinnerung} ${m.erinnerung === 1 ? 'Mitarbeiter' : 'Mitarbeiter'} mit E-Mail-Adresse, bei denen Resturlaub aus dem Vorjahr verfällt` : 'Bei niemandem mit E-Mail-Adresse verfällt gerade Resturlaub.'}${m.erinnerungOhneAdresse ? ` · ${m.erinnerungOhneAdresse} ohne E-Mail-Adresse (nicht erreichbar)` : ''}</p>
        <button type="button" class="btn" data-hr-mail="erinnerung"${m.erinnerung ? '' : ' disabled'}>${icon('mail', 'sm')}Erinnerung senden</button>
      </div>
      <div class="hr-mail-block">
        <h4>Monatsübersicht an die Mitarbeiter</h4>
        <p class="hint">Jeder Mitarbeiter im Urlaubsplan bekommt seinen Urlaub im Vormonat und seinen Stand im Jahr (Krankheit steht nie darin). ${m.empfaenger} mit E-Mail-Adresse${m.ohneAdresse ? `, ${m.ohneAdresse} ohne` : ''}. „Jetzt senden“: für ${esc(monatText(vor))}.</p>
        <label class="check hr-mail-check"><input type="checkbox" id="hrm-monat-an"${e.monat.an ? ' checked' : ''}> <span>Automatisch jeden Monat ab dem 1.${klein(n.monat ? `Nächster Versand: ${esc(datumDe(n.monat))} (für ${esc(monatText(n.monat.slice(0, 7) === dies ? vor : dies))})` : '')}</span></label>
        <button type="button" class="btn" data-hr-mail="monat"${m.empfaenger ? '' : ' disabled'}>${icon('mail', 'sm')}Jetzt senden</button>
      </div>
      <div class="hr-mail-block">
        <h4>Übersicht an den Steuerberater</h4>
        <p class="hint">Excel-Übersicht wie der Export (alle genehmigten Abwesenheiten) für den Vormonat und den laufenden Monat – jetzt: ${esc(monatText(vor))} und ${esc(monatText(dies))}.</p>
        <div class="form-grid two">
          <label class="fld"><span>E-Mail-Adresse des Steuerberaters</span><input type="email" id="hrm-stb-adresse" value="${esc(e.steuerberater.adresse)}" maxlength="200" autocomplete="off" placeholder="name@kanzlei.de"></label>
          <label class="fld"><span>Versand am</span><select id="hrm-stb-tag">${Array.from({ length: 28 }, (_, i) => `<option value="${i + 1}"${e.steuerberater.tag === i + 1 ? ' selected' : ''}>${i + 1}. des Monats</option>`).join('')}</select></label>
        </div>
        <label class="check hr-mail-check"><input type="checkbox" id="hrm-stb-an"${e.steuerberater.an ? ' checked' : ''}> <span>Automatisch am gewählten Tag${klein(n.steuerberater ? `Nächster Versand: ${esc(datumDe(n.steuerberater))}` : '')}</span></label>
        <button type="button" class="btn" data-hr-mail="steuerberater"${e.steuerberater.adresse ? '' : ' disabled'}>${icon('mail', 'sm')}Jetzt senden</button>
      </div>
      <div class="hr-mail-block">
        <h4>Testmodus</h4>
        <label class="check hr-mail-check"><input type="checkbox" id="hrm-test-an"${e.test.an ? ' checked' : ''}> <span>Alle HR-E-Mails nur an die Testadresse${klein('Monatsübersicht, Erinnerung, Steuerberater und Bitte um Erklärung bei unentschuldigtem Fehlen – automatisch und auf Knopfdruck; der Betreff nennt den eigentlichen Empfänger.')}</span></label>
        <label class="fld hr-mail-test"><span>Testadresse</span><input type="email" id="hrm-test-adresse" value="${esc(e.test.adresse)}" maxlength="200" autocomplete="off"></label>
      </div>
      ${verlauf ? `<h4 class="hr-mail-vh">Zuletzt gesendet</h4><ul class="hr-mail-verlauf" id="hrm-verlauf">${verlauf}</ul>` : ''}
      <p class="form-err" id="hr-mail-err" role="alert"></p>
      <div class="sec-foot"><span class="hint" id="hr-mail-hinweis"></span><button type="submit" class="btn primary">${icon('check', 'sm')}Speichern</button></div></form>`;
  }
  const mailWerte = () => ({ monat: { an: $('#hrm-monat-an').checked }, test: { an: $('#hrm-test-an').checked, adresse: $('#hrm-test-adresse').value.trim() },
    steuerberater: { an: $('#hrm-stb-an').checked, adresse: $('#hrm-stb-adresse').value.trim(), tag: Number($('#hrm-stb-tag').value) } });
  function mailNeu(m) { daten.mail = m; const alt = $('#hr-mail'); if (alt) alt.outerHTML = mailKarte(); }
  // Nach einer Änderung erst speichern: die Knöpfe senden mit den gespeicherten Einstellungen
  const mailGeaendert = (e) => {
    if (!e.target.closest('#hr-mail') || e.target.closest('[data-hr-mail]')) return;
    $$('#hr-mail [data-hr-mail]').forEach((b) => { b.disabled = true; });
    $('#hr-mail-hinweis').textContent = 'Geändert – bitte speichern, dann senden.';
  };
  document.addEventListener('input', mailGeaendert);
  document.addEventListener('change', mailGeaendert);
  document.addEventListener('submit', async (e) => {
    if (e.target.id !== 'hr-mail') return;
    e.preventDefault();
    $('#hr-mail-err').textContent = '';
    try {
      const r = await api('hr_mail_save', { body: mailWerte() });
      mailNeu(r.mail);
      toast('E-Mail-Einstellungen gespeichert.');
    } catch (ex) { $('#hr-mail-err').textContent = ex.message; }
  });
  document.addEventListener('click', async (e) => {
    const b = e.target.closest('#hr-mail [data-hr-mail]');
    if (!b || b.disabled) return;
    const m = daten.mail, [vor, dies] = m.monate, test = m.einst.test.an ? ` Testmodus: alles geht nur an ${m.einst.test.adresse}.` : '';
    const art = b.dataset.hrMail;
    const frage = {
      erinnerung: ['Erinnerung senden?', `${m.erinnerung} Mitarbeiter bekommen eine E-Mail, dass ihr Resturlaub aus dem Vorjahr verfällt.${test}`, 'hr_erinnerung_senden', {}],
      monat: ['Monatsübersicht senden?', `${m.empfaenger} Mitarbeiter bekommen ihre Übersicht für ${monatText(vor)}.${test}`, 'hr_monatsuebersicht_senden', { monat: vor }],
      steuerberater: ['Übersicht an den Steuerberater senden?', `Die Excel-Übersicht für ${monatText(vor)} und ${monatText(dies)} geht an ${m.einst.steuerberater.adresse}.${test}`, 'hr_steuerberater_senden', {}],
    }[art];
    if (!(await confirmBox(frage[0], esc(frage[1]), 'Senden'))) return;
    b.disabled = true; $('#hr-mail-err').textContent = '';
    try {
      const r = await api(frage[2], { body: frage[3] });
      mailNeu(r.mail);
      const x = r.ergebnis;
      toast(`${x.gesendet} ${x.gesendet === 1 ? 'E-Mail' : 'E-Mails'} gesendet${x.fehler ? `, ${x.fehler} nicht zugestellt` : ''}${x.test ? ' (Testmodus)' : ''}.`, x.fehler ? 8000 : 4000);
    } catch (ex) { b.disabled = false; $('#hr-mail-err').textContent = ex.message; }
  });
  document.addEventListener('click', (e) => {
    const plus = e.target.closest('#hr-einst [data-plus]');
    if (plus) $('#' + plus.dataset.plus).insertAdjacentHTML('beforeend', zeile({}));
    const weg = e.target.closest('#hr-einst [data-weg]');
    if (weg) weg.parentElement.remove();
    if (e.target.closest('#hr-regeln-vorlage') && daten) $('#hr-regeln').value = daten.regelnStandard || '';
    const alt = e.target.closest('[data-hr-alt]');
    if (alt) altbestandUebernehmen(alt, async () => { await laden(); if (W.views.users) W.views.users(); });
    if (e.target.closest('[data-hr-alt-einzeln]')) altDialog(async () => { if (W.views.users) W.views.users(); });
    const tr = e.target.closest('tr[data-hr-uid]');
    if (tr) nurHrDialog(tr.dataset.hrUid, $('#view-users'));
  });
  document.addEventListener('submit', async (e) => {
    if (e.target.id !== 'hr-einst') return;
    e.preventDefault();
    const liste = (id) => $$('#' + id + ' .hr-zr').map((z) => { const i = $$('input', z); return { von: i[0].value, bis: i[1].value, text: i[2].value }; });
    try {
      const bis = $('#hr-uebertrag-bis').value;
      if (!bis) { $('#hr-einst-err').textContent = 'Bitte den Verfallstag des Resturlaubs wählen.'; return; }
      const ab = $('#hr-verfall-ab').value;
      const r = await api('hr_einstellungen_save', { body: { sperren: liste('hr-sperren'), ferien: liste('hr-ferien'), uebertragBis: bis,
        verfallAb: ab ? Number(ab) : null, regelSperren: $('#hr-regelsperren').checked, regeln: $('#hr-regeln').value } });
      Object.assign(daten, { sperren: r.sperren, ferien: r.ferien, uebertragBis: r.uebertragBis, verfallAb: r.verfallAb, regelSperren: r.regelSperren, sperrenAuto: r.sperrenAuto, regeln: r.regeln });
      toast('Urlaubseinstellungen gespeichert.');
      renderUrlaub();
    } catch (ex) { $('#hr-einst-err').textContent = ex.message; }
  });
  // Schalter „Urlaubsanträge über die Plattform“: speichert sofort; bei einem Fehler springt er zurück
  document.addEventListener('change', async (e) => {
    if (e.target.id !== 'hr-antraege') return;
    const sw = e.target, an = sw.checked;
    sw.disabled = true; $('#hr-antraege-err').textContent = '';
    try {
      const r = await api('hr_antraege_save', { body: { an } });
      if (daten) daten.antraege = r.antraege;
      $('#hr-antraege-t').textContent = r.antraege ? 'Eingeschaltet' : 'Ausgeschaltet';
      toast(r.antraege ? 'Urlaubsanträge eingeschaltet.' : 'Urlaubsanträge ausgeschaltet.');
    } catch (ex) {
      sw.checked = !an;
      $('#hr-antraege-err').textContent = ex.message;
    } finally { sw.disabled = false; }
  });
  W.views.urlaub = renderUrlaub;

  /* ---------- Importzentrale ---------- */
  W.importLeser = W.importLeser || {};

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
