/* STAFL-Plattform · Angebot · Fenster „Angebot kopieren“ (Entscheidung des Inhabers 13.11.2026). Geöffnet über „Kopieren“
   im Kopf des gewählten Angebots (Angebot bearbeiten) und je Angebot unter Stammdaten → Angebote. Name der Kopie vorbelegt
   („Kopie von …“, bei Bedarf mit Nummer), dazu, was mitkommt: Artikel mit Preisen, eigene Bezeichnungen, Empfehlungen und
   Sonderposten, Werbung – nie die Kunden (Kundengruppen bleiben leer). Hinweis: Kunden sehen die Kopie erst mit
   zugeordneten Kundengruppen und nach dem Veröffentlichen. Kopiert wird auf dem Server (offer_kopieren,
   app/api/module/angebot/kopieren.php) über admin.js (WA.angebot.kopie.ausfuehren: vorher speichern, danach Angebotsliste
   und Entwurf übernehmen, neues Angebot im Editor wählen). Rechte prüft der Server; den Knopf zeigt admin.js nur mit
   „Kundenangebote anlegen“ und „Entwurf bearbeiten“.
   Wird von admin/index.html nach admin.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  const dlg = document.getElementById('dlg-angebot-kopieren');
  const form = document.getElementById('angebot-kopieren-body');
  if (!W || !dlg || !form || !W.angebot || !W.angebot.kopie) return;
  const { esc, icon, plural, toast } = W;
  const K = W.angebot.kopie;
  let d = null;          // Daten beim Öffnen (admin.js kopieDaten): { quelle, name, std, folgt, artikel, namen, werbung, vergeben }
  let busy = false;

  const klein = (t) => String(t || '').toLocaleLowerCase('de');
  const vergeben = (name) => d.vergeben.some((n) => klein(n) === klein(name));
  /* Vorschlag „Kopie von …“; ist der Name schon vergeben, mit fortlaufender Nummer (höchstens 80 Zeichen wie auf dem Server) */
  function vorschlag() {
    const basis = ('Kopie von ' + d.name).slice(0, 80);
    if (!vergeben(basis)) return basis;
    for (let k = 2; ; k++) { const n = `${basis.slice(0, 74)} (${k})`; if (!vergeben(n)) return n; }
  }
  function oeffnen(oid) {
    d = K.daten(oid);
    busy = false;
    const was = [d.std ? `${plural(d.artikel, 'Artikel', 'Artikel')} des Wochenangebots, der Wochenpreis als eigener Preis` : `${plural(d.artikel, 'Artikel', 'Artikel')} mit ihren Preisen`];
    if (d.namen) was.push(plural(d.namen, 'eigene Bezeichnung', 'eigene Bezeichnungen'));
    was.push('Empfehlungen und Sonderposten');
    if (d.werbung) was.push('Werbung');
    form.innerHTML = `<div class="dlg-head"><div><h2 id="ak-titel">Angebot kopieren</h2><p>Aus <strong>${esc(d.name)}</strong> entsteht ein neues Kundenangebot, das Sie danach frei ändern können. Das Original bleibt unverändert.</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <label class="fld"><span>Name des neuen Angebots</span><input name="name" id="ak-name" maxlength="80" autocomplete="off" spellcheck="false" value="${esc(vorschlag())}"></label>
        <p class="hint ak-was" id="ak-was"><strong>Wird mitkopiert:</strong> ${esc(was.join(' · '))}${d.folgt ? ' · Einstellung „folgt dem Wochenangebot“' : d.std ? ' · als eigene Artikelliste' : ''}.<br><strong>Nicht mitkopiert:</strong> Kundengruppen und Kunden.</p>
        <div class="notice ak-hinweis" id="ak-hinweis">${icon('info', 'sm')}<span>Kunden sehen die Kopie erst, wenn ihr unter Stammdaten → Angebote Kundengruppen zugeordnet sind und das Angebot veröffentlicht ist. Jede Kundengruppe gehört zu genau einem Angebot.</span></div>
        <p class="form-err" id="ak-err" role="alert"></p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary" id="ak-ok">${icon('copy')}Kopieren</button></div>`;
    dlg.showModal();
    const inp = form.querySelector('#ak-name');
    inp.focus(); inp.select();
  }
  function fehler(t) { form.querySelector('#ak-err').textContent = t; }
  form.addEventListener('input', (e) => { if (e.target.id === 'ak-name') fehler(''); });
  form.addEventListener('click', (e) => { if (e.target.closest('[data-close]') && !busy) dlg.close(); });
  dlg.addEventListener('cancel', (e) => { if (busy) e.preventDefault(); });   // während des Kopierens nicht schließen
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (busy || !d) return;
    const name = form.elements.name.value.replace(/\s+/g, ' ').trim();
    if (name.length < 2) { fehler('Bitte einen Namen angeben (mindestens 2 Zeichen).'); return; }
    if (vergeben(name)) { fehler(`Der Name „${name}“ ist bereits vergeben.`); return; }
    const ok = form.querySelector('#ak-ok');
    busy = true; ok.disabled = true; ok.textContent = 'Wird kopiert …';
    try {
      const r = await K.ausfuehren(d.quelle, name);
      busy = false;
      dlg.close();
      toast(`„${r.name}“ angelegt – ${plural(r.artikel, 'Artikel', 'Artikel')} im Entwurf. Kundengruppen unter Stammdaten → Angebote zuordnen.`, 7000);
    } catch (ex) {
      busy = false;
      ok.disabled = false; ok.innerHTML = `${icon('copy')}Kopieren`;
      fehler(ex.message);
    }
  });
  K.oeffnen = oeffnen;
})();
