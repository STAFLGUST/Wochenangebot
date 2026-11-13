/* STAFL-Plattform · Angebot · Drucken aus „Angebot bearbeiten“ und Einstellung „Fußzeile im Druck“ (Wunsch des Inhabers 13.11.2026).
   Knopf „Drucken“ (#btn-drucken, Kopfleiste links neben „An Kunden senden“/„Veröffentlichen“): druckt das gewählte Angebot so,
   wie die Vorschau es zeigt – den gespeicherten Entwurf in der Angebotsansicht (A4 quer, kompakt, mit Hinweis und Fußzeile).
   Dazu lädt er die Angebotsseite unsichtbar (iframe, ?vorschau=1&drucken=liste); sie setzt die Druckfassung
   (assets/angebot-druck.js) und öffnet den Druckdialog des Browsers – dort auch „Als PDF speichern“. Dieselbe Fassung
   drucken „Drucken“ im Vorschaufenster und der Druckdialog der Angebotsseite (Layout „Angebotsansicht“).
   „Fußzeile im Druck“ (Menü ⋯, nur Administratoren; der Server prüft das beim Speichern): drei Spalten und zwei Zeilen des
   Briefbogens, die Wahl „auf jeder Seite“ / „nur auf der letzten Seite“ und der Schalter „Bankangaben nur für angemeldete
   Nutzer“ – Aktionen druck_fuss / druck_fuss_save (api/module/angebot/druck.php). Leere Felder = Vorgabe aus dem Impressum.
   Für andere Module: WA.angebot.druck.drucken({ angebot, entwurf, name, knopf }) druckt ein beliebiges Angebot in derselben Fassung.
   Wird von admin/index.html nach admin.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  const btn = document.getElementById('btn-drucken');
  if (!W || !btn || !W.angebot || !W.angebot.druck) return;
  const { $, api, esc, icon, toast } = W;
  const D = W.angebot.druck;

  /* ---------- Drucken ----------
     drucken({ adresse | angebot, entwurf, name, knopf }) lädt die Angebotsseite unsichtbar mit „drucken=liste“; sie setzt die
     Druckfassung, öffnet den Druckdialog und meldet sich (postMessage {wa: 'druck', stand: 'bereit' | 'gedruckt' | 'fehler'}).
     Auch für andere Module (WA.angebot.druck.drucken), z. B. die Liste „Angebote dieser Woche“ im Versand:
     angebot = Kennung (ohne Angabe das Wochenangebot, „e-…“ = Einzelangebot), entwurf = true druckt den Entwurf statt des
     veröffentlichten Stands; knopf wird währenddessen gesperrt. */
  let frame = null, uhr = 0, aktiv = null;
  function fertig() {
    clearTimeout(uhr);
    if (aktiv) { aktiv.disabled = false; aktiv.removeAttribute('aria-busy'); }
    aktiv = null;
  }
  function drucken(opt) {
    const o = opt || {}, url = o.adresse || D.adresseFuer(o.angebot || '', !!o.entwurf);
    if (!url) return false;
    fertig();
    aktiv = o.knopf || null;
    if (aktiv) { aktiv.disabled = true; aktiv.setAttribute('aria-busy', 'true'); }
    if (frame) frame.remove();
    frame = document.createElement('iframe');
    frame.id = 'druck-frame';
    frame.className = 'druck-frame';
    frame.title = 'Druckfassung des Angebots';
    frame.setAttribute('aria-hidden', 'true');
    frame.tabIndex = -1;
    frame.src = url + (url.includes('?') ? '&' : '?') + 'drucken=liste';
    document.body.append(frame);
    toast(`Druckfassung${o.name ? ` von „${o.name}“` : ''} wird vorbereitet${o.entwurf ? ' (Entwurf, wie in der Vorschau)' : ''} …`, 4000);
    // die Seite meldet „bereit“ (Druckdialog öffnet sich) bzw. „gedruckt“; ohne Meldung (z. B. Sitzung beendet) wieder freigeben
    uhr = setTimeout(() => { fertig(); toast('Die Druckfassung konnte nicht geladen werden. Bitte erneut versuchen.', 6000); }, 20000);
    return true;
  }
  D.drucken = drucken;
  window.addEventListener('message', (e) => {
    if (e.origin !== location.origin || !frame || e.source !== frame.contentWindow || !e.data || e.data.wa !== 'druck') return;
    if (e.data.stand === 'bereit' || e.data.stand === 'gedruckt') fertig();
    if (e.data.stand === 'fehler') { fertig(); toast('Die Druckfassung konnte nicht geladen werden. Bitte erneut versuchen.', 6000); }
  });
  // Knopf „Drucken“: das gewählte Angebot, wie die Vorschau es zeigt – vorher den Entwurf speichern
  btn.addEventListener('click', async () => {
    if (btn.disabled) return;
    btn.disabled = true;
    try {
      await D.bereit();
      btn.disabled = false;
      drucken({ adresse: D.adresse(), name: D.name(), entwurf: true, knopf: btn });
    } catch (e) {
      btn.disabled = false;
      if (e && e.status !== 401) toast((e && e.message) || 'Drucken nicht möglich.', 6000);
    }
  });

  /* ---------- Fußzeile im Druck (nur Administratoren) ---------- */
  const dlg = $('#dlg-druck-fuss'), body = $('#druck-fuss-body');
  const eintrag = $('#menu-more [data-act="druck-fuss"]');
  const admin = () => !!(W.me && W.me.role === 'admin');
  let daten = null;
  function fussForm() {
    const f = daten.fuss, sp = f.eigen ? f.spalten : ['', '', ''], ze = f.eigen ? f.zeilen : ['', ''], v = daten.vorgabe;
    const titel = ['Spalte 1 – Firma und Anschrift', 'Spalte 2 – Telefon, Web, E-Mail', 'Spalte 3 – Bank und Steuer'];
    body.innerHTML = `<div class="dlg-head"><div><h2 id="df-titel">${icon('print')}Fußzeile im Druck</h2>
        <p>Steht unter jedem gedruckten Angebot (Wochenangebot, Kundenangebote, Einzelangebote), darüber der Hinweis zu Mengen und Fracht. Leere Felder: es gilt die Vorgabe aus dem Impressum.</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <div class="df-spalten">${sp.map((t, i) => `<label class="fld"><span>${titel[i]}</span><textarea name="s${i}" rows="6" maxlength="460" placeholder="${esc(v.spalten[i])}">${esc(t)}</textarea></label>`).join('')}</div>
        ${ze.map((t, i) => `<label class="fld"><span>Zeile ${i + 1} – Handelsregister</span><input name="z${i}" maxlength="200" value="${esc(t)}" placeholder="${esc(v.zeilen[i])}"></label>`).join('')}
        <fieldset class="choice df-modus"><legend>Fußzeile und Hinweis stehen</legend>
          <label class="radio"><input type="radio" name="modus" value="jede"${f.modus === 'jede' ? ' checked' : ''}><span class="r-t">auf jeder Seite</span></label>
          <label class="radio"><input type="radio" name="modus" value="letzte"${f.modus === 'letzte' ? ' checked' : ''}><span class="r-t">nur auf der letzten Seite<span class="r-s">spart Platz – meist eine Seite weniger</span></span></label>
        </fieldset>
        <label class="check df-bank"><input type="checkbox" name="bank"${f.bankGeschuetzt ? ' checked' : ''}><span>Bankangaben (Spalte 3) nur für angemeldete Nutzer<span class="r-s">Kunden mit Zugang und Mitarbeiter sehen die ganze Fußzeile. Ohne Anmeldung – im öffentlichen Wochenangebot – steht in Spalte 3 nur die Angabe aus dem Impressum.</span></span></label>
        <div class="df-hinweis"><span>Hinweis über der Fußzeile (aus Verwaltung → E-Mail → „Fracht und Hinweis im Angebot“)</span><p>${(daten.hinweis || []).map(esc).join('<br>') || '–'}</p></div>
        <p class="hint" id="df-stand">${f.eigen ? `Zuletzt geändert${f.updatedBy ? ' von ' + esc(f.updatedBy) : ''}${f.updatedAt ? ' am ' + esc(W.dateTime(f.updatedAt)) : ''}.` : 'Noch keine eigenen Texte – es gilt die Vorgabe (grau in den Feldern).'}</p>
        <p class="form-err" id="df-err" role="alert"></p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn ghost" id="df-vorgabe" title="Die Vorgabe in die Felder schreiben, um sie zu ergänzen">Vorgabe einsetzen</button><span class="spacer"></span>
        <button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary" id="df-ok">${icon('check')}Speichern</button></div>`;
  }
  async function fussOeffnen() {
    if (!admin()) return;
    try { daten = await api('druck_fuss'); } catch (e) { if (e.status !== 401) toast(e.message || 'Die Fußzeile konnte nicht geladen werden.', 6000); return; }
    fussForm();
    dlg.showModal();
    body.querySelector('textarea').focus();
  }
  body.addEventListener('click', (e) => {
    if (!e.target.closest('#df-vorgabe') || !daten) return;
    daten.vorgabe.spalten.forEach((t, i) => { const el = body.elements['s' + i]; if (!el.value.trim()) el.value = t; });
    daten.vorgabe.zeilen.forEach((t, i) => { const el = body.elements['z' + i]; if (!el.value.trim()) el.value = t; });
    dlg.dataset.geaendert = '1';
  });
  body.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ok = $('#df-ok'), err = $('#df-err'), el = body.elements;
    err.textContent = '';
    ok.disabled = true; dlg.dataset.busy = '1';
    try {
      const r = await api('druck_fuss_save', { body: { fuss: { spalten: [0, 1, 2].map((i) => el['s' + i].value), zeilen: [0, 1].map((i) => el['z' + i].value), modus: el.modus.value, bankGeschuetzt: el.bank.checked } } });
      delete dlg.dataset.geaendert;
      delete dlg.dataset.busy;
      dlg.close();
      toast(`Fußzeile im Druck gespeichert – ${r.fuss.modus === 'letzte' ? 'nur auf der letzten Seite' : 'auf jeder Seite'}${r.fuss.eigen ? '' : ' (Vorgabe aus dem Impressum)'}.`, 5000);
    } catch (ex) {
      delete dlg.dataset.busy;
      ok.disabled = false;
      if (ex.status !== 401) err.textContent = ex.message || 'Nicht gespeichert.';
    }
  });
  $('#menu-more').addEventListener('click', (e) => { if (e.target.closest('[data-act="druck-fuss"]')) fussOeffnen(); });
  // Menüeintrag nur für Administratoren (beim Öffnen des Menüs: die Anmeldung steht dann fest)
  $('#btn-more').addEventListener('click', () => { if (eintrag) eintrag.hidden = !admin(); });
})();
