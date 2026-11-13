/* STAFL-Plattform · Angebot · Fenster „Frühere Wochen“ (Wunsch des Inhabers 13.11.2026): frühere Wochenangebote ansehen und
   die KW wechseln wie in der REWE-Liste – Pfeile ‹ ›, Titel „<Angebot> · KW 43/2026“, „Diese Woche“, Adresse #woche/JJJJ-WW.
   Nur Mitarbeiter mit Modulzugang Angebot, nur lesend. Einstieg: Menü ⋯ → „Frühere Wochen“ im Eingabebereich oder die
   Adresse …/admin/#woche/2026-43. Auswahl des Angebots (Wochenangebot oder Kundenangebot, gemerkt in diesem Browser).
   Inhalt: die Angebotsseite im Rahmen (wie die Vorschau, ../index.html?vorschau=1&eingebettet=1&woche=…), die über die Aktion
   angebot_woche den zuletzt veröffentlichten Stand der KW lädt – aufgelöst auf dem Server (app/api/module/angebot/wochen.php,
   offer_resolve, GR-002/GR-005). Kopf und Hinweise aus derselben Aktion: Quelle (aktuell veröffentlicht, frühere
   Veröffentlichung aus der Wochenablage oder den Versionen, oder nur Preisstand aus dem Preisverlauf), Stand; Kundenangebote
   mit ihrer damaligen Einstellung, sonst ein Hinweis; gab es das Angebot in der Woche nicht, ein Hinweis statt der Seite; ohne
   gespeicherten Stand ein Hinweis mit Sprung zur letzten gespeicherten Woche. KW-Rechnung nach dem Muster der REWE-Liste (isoKw, kwPlus), nicht aus dem REWE-Modul geladen.
   Wird von admin/index.html nach admin.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  const dlg = document.getElementById('dlg-wochen');
  const body = document.getElementById('wochen-body');
  const eintrag = document.querySelector('#menu-more [data-act="wochen"]');
  if (!W || !dlg || !body) return;
  const { api, esc, icon } = W;
  const F = window.STAFL_FORMAT;
  const MERK = 'wa.fruehereWochen.angebot';
  const S = { woche: '', angebot: 'std', d: null, nr: 0 };
  const darf = () => !!(W.me && W.may && W.may('angebot.zugang'));

  /* ---------- Kalenderwochen (ISO, „JJJJ-WW“) wie in der REWE-Liste ---------- */
  function montag(kw) {
    const j = +kw.slice(0, 4), w = +kw.slice(5, 7);
    const d = new Date(Date.UTC(j, 0, 4)); const t = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() - t + 1 + (w - 1) * 7);
    return d;
  }
  function isoKw(d) {
    const x = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));   // Datum in Ortszeit (Server und Tests: Europe/Berlin)
    const t = x.getUTCDay() || 7; x.setUTCDate(x.getUTCDate() + 4 - t);
    const j = x.getUTCFullYear(); const w = Math.ceil(((x - Date.UTC(j, 0, 1)) / 86400000 + 1) / 7);
    return `${j}-${String(w).padStart(2, '0')}`;
  }
  const kwPlus = (kw, n) => { const d = montag(kw); d.setUTCDate(d.getUTCDate() + 7 * n); const x = new Date(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()); return isoKw(x); };
  const kwText = (kw) => F.kw(+kw.slice(5), kw.slice(0, 4));
  const kwOk = (v) => /^\d{4}-\d{2}$/.test(v) && +v.slice(5) >= 1 && +v.slice(5) <= 53;
  const heute = () => isoKw(new Date());
  function zeitraum(kw) {
    const a = montag(kw), b = new Date(a); b.setUTCDate(b.getUTCDate() + 6);
    const t = (d, jahr) => `${String(d.getUTCDate()).padStart(2, '0')}.${String(d.getUTCMonth() + 1).padStart(2, '0')}.${jahr ? d.getUTCFullYear() : ''}`;
    return `${t(a, false)}–${t(b, true)}`;
  }
  const merken = (v) => { try { localStorage.setItem(MERK, v); } catch { /* ohne Speicher */ } };
  const gemerkt = () => { try { return localStorage.getItem(MERK) || 'std'; } catch { return 'std'; } };
  const adresse = (kw, oid) => '../index.html?vorschau=1&eingebettet=1&woche=' + kw + (oid && oid !== 'std' ? '&angebot=' + encodeURIComponent(oid) : '') + '&t=' + Date.now();

  function geruest() {
    body.innerHTML = `<div class="dlg-head pv-head fw-head">
        <div class="fw-nav">
          <button type="button" class="btn icon ghost" data-fw="zurueck" aria-label="Vorige Woche" title="Vorige Woche">${icon('back')}</button>
          <div class="fw-t"><h2 id="fw-titel">Frühere Wochen</h2><p id="fw-sub"></p></div>
          <button type="button" class="btn icon ghost fw-vor" data-fw="vor" aria-label="Nächste Woche" title="Nächste Woche">${icon('back')}</button>
        </div>
        <button type="button" class="btn sm ghost fw-heute" data-fw="heute" hidden>Diese Woche</button>
        <label class="pv-sel"><span class="sr-only">Angebot</span><select id="fw-angebot" aria-label="Angebot"></select></label>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="fw-hinweis" id="fw-hinweis" role="status" hidden></div>
      <div class="pv-main"><div class="pv-stage laden" id="fw-stage">
        <iframe id="fw-frame" title="Angebot der gewählten Woche"></iframe>
        <div class="pv-laden"><div class="spinner"></div>Angebot wird geladen …</div>
        <div class="fw-leer" id="fw-leer" hidden></div>
      </div></div>`;
    body.querySelector('#fw-frame').addEventListener('load', () => body.querySelector('#fw-stage').classList.remove('laden'));
  }
  function kopf() {
    const d = S.d, name = d ? d.angebot.name : '';
    body.querySelector('#fw-titel').innerHTML = `${name ? esc(name) + ' · ' : ''}<span class="fw-kw">${esc(kwText(S.woche))}</span>`;
    const teile = [zeitraum(S.woche)];
    if (d && d.quelle === 'veroeffentlicht') teile.push('aktuell veröffentlicht' + (d.stand ? ' · ' + F.datumZeit(d.stand) : ''));
    else if (d && (d.quelle === 'ablage' || d.quelle === 'version')) teile.push('zuletzt veröffentlicht' + (d.stand ? ' ' + F.datumZeit(d.stand) : ''));
    else if (d && d.quelle === 'historie') teile.push('nur Preisstand');
    if (d && d.quelle) teile.push(`${d.artikel} Artikel`);
    body.querySelector('#fw-sub').textContent = teile.join(' · ');
    const h = heute(), letzte = d && d.naechste && d.naechste > h ? d.naechste : h;
    body.querySelector('[data-fw="zurueck"]').disabled = !!d && !d.vorige;
    body.querySelector('[data-fw="vor"]').disabled = S.woche >= letzte;
    body.querySelector('[data-fw="heute"]').hidden = S.woche === h;
    const sel = body.querySelector('#fw-angebot');
    if (d) sel.innerHTML = d.angebote.map((o) => `<option value="${esc(o.id)}"${o.id === d.angebot.id ? ' selected' : ''}>${esc(o.name)}</option>`).join('');
  }
  function hinweis(text) {
    const el = body.querySelector('#fw-hinweis');
    el.hidden = !text;
    el.innerHTML = text ? `${icon('info', 'sm')}<span>${text}</span>` : '';
  }
  async function laden() {
    const nr = ++S.nr;
    try { history.replaceState(null, '', '#woche/' + S.woche); } catch { /* ohne Verlauf */ }
    const stage = body.querySelector('#fw-stage'), frame = body.querySelector('#fw-frame'), leer = body.querySelector('#fw-leer');
    stage.classList.add('laden'); leer.hidden = true; hinweis('');
    kopf();
    let d;
    try { d = await api('angebot_woche', { query: '&woche=' + S.woche + '&angebot=' + encodeURIComponent(S.angebot) }); }
    catch (e) {
      if (nr !== S.nr) return;
      stage.classList.remove('laden'); frame.hidden = true; leer.hidden = false;
      leer.innerHTML = `<div class="err-box">${esc(e.message)}</div>`;
      if (e.status === 404 && S.angebot !== 'std') { S.angebot = 'std'; merken('std'); laden(); }   // gemerktes Angebot gibt es nicht mehr
      return;
    }
    if (nr !== S.nr) return;
    S.d = d;
    kopf();
    if (!d.offer && d.fehlt) {   // Kundenangebot gab es in dieser Woche noch nicht (Wochenablage mit den damaligen Angeboten)
      stage.classList.remove('laden'); frame.hidden = true; frame.removeAttribute('src'); leer.hidden = false;
      leer.innerHTML = `<p><strong>„${esc(d.angebot.name)}“ gab es in ${esc(kwText(S.woche))} noch nicht.</strong></p>
        <p class="hint">Das Wochenangebot dieser Woche ist gespeichert – oben ein anderes Angebot wählen.</p>`;
      return;
    }
    if (!d.offer) {
      stage.classList.remove('laden'); frame.hidden = true; frame.removeAttribute('src'); leer.hidden = false;
      leer.innerHTML = `<p><strong>Für ${esc(kwText(S.woche))} ist kein Angebot gespeichert.</strong></p>
        <p class="hint">${d.vorige ? 'Gespeichert sind veröffentlichte Angebote und der Preisverlauf.' : 'Davor sind keine Wochen gespeichert.'}</p>
        ${d.vorige ? `<button type="button" class="btn" data-fw="gehe" data-kw="${esc(d.vorige)}">${icon('back', 'sm')}Zur letzten gespeicherten Woche (${esc(kwText(d.vorige))})</button>` : ''}`;
      return;
    }
    // Kundenangebot ohne gespeicherte Definition dieser Woche (vor der Wochenablage): Artikel nach der heutigen Einstellung
    const heute = d.angebot.id !== 'std' && d.einstellung !== 'damals' && d.quelle !== 'veroeffentlicht';
    if (d.quelle === 'historie') hinweis(`Für diese Woche ist nur noch der Preisstand gespeichert (Preisverlauf): Artikel und Preise nach Angebotsgruppen – ohne Werbung, Bereiche, eigene Bezeichnungen und Empfehlungen.${heute ? ' Artikel des Kundenangebots nach seiner heutigen Einstellung.' : ''}`);
    else if (heute) hinweis('Artikel des Kundenangebots nach seiner heutigen Einstellung (eigene Artikelliste oder „folgt dem Wochenangebot“) – für diese Woche ist sie nicht gespeichert.');
    frame.hidden = false;
    frame.src = adresse(S.woche, d.angebot.id);
  }
  function oeffnen(kw) {
    if (!darf()) return;
    S.woche = kwOk(kw || '') ? kw : heute();
    if (!dlg.open) {
      S.angebot = gemerkt(); S.d = null;
      geruest();
      dlg.showModal();
    }
    laden();
  }
  function gehe(kw) { if (!kwOk(kw) || kw === S.woche) return; S.woche = kw; laden(); }

  body.addEventListener('click', (e) => {
    if (e.target.closest('[data-close]')) { dlg.close(); return; }
    const b = e.target.closest('[data-fw]');
    if (!b || b.disabled) return;
    const a = b.dataset.fw;
    if (a === 'zurueck') gehe(kwPlus(S.woche, -1));
    if (a === 'vor') gehe(kwPlus(S.woche, 1));
    if (a === 'heute') gehe(heute());
    if (a === 'gehe') gehe(b.dataset.kw);
  });
  body.addEventListener('change', (e) => {
    if (e.target.id !== 'fw-angebot') return;
    S.angebot = e.target.value; merken(S.angebot); laden();
  });
  dlg.addEventListener('close', () => {
    S.nr++;
    const f = body.querySelector('#fw-frame'); if (f) f.removeAttribute('src');
    if (/^#woche\//.test(location.hash)) { try { history.replaceState(null, '', location.pathname + location.search); } catch { /* ohne Verlauf */ } }
  });
  const ausAdresse = () => { const m = location.hash.match(/^#woche\/(\d{4}-\d{2})$/); return m && kwOk(m[1]) ? m[1] : ''; };
  window.addEventListener('hashchange', () => { const kw = ausAdresse(); if (kw && (!dlg.open || kw !== S.woche)) oeffnen(kw); });
  // Menü ⋯ → „Frühere Wochen“ (nur mit Modulzugang Angebot – die verbindliche Prüfung macht der Server)
  if (eintrag) {
    document.getElementById('btn-more').addEventListener('click', () => { eintrag.hidden = !darf(); });
    document.getElementById('menu-more').addEventListener('click', (e) => { if (e.target.closest('[data-act="wochen"]')) oeffnen(heute()); });
  }
  // Aufruf mit #woche/JJJJ-WW: öffnen, sobald der Eingabebereich angemeldet zu sehen ist
  const editor = document.getElementById('screen-editor');
  if (ausAdresse() && editor) {
    const start = () => { if (!editor.hidden && darf() && ausAdresse()) { beob.disconnect(); oeffnen(ausAdresse()); } };
    const beob = new MutationObserver(start);
    beob.observe(editor, { attributes: true, attributeFilter: ['hidden'] });
    start();
  }
})();
