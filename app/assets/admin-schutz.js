/* ==========================================================================
   Wochenangebot – Eingabebereich, Schutz (nur Administratoren)
   Firewall, Sperrliste (von Hand, automatisch, Bedrohungsliste), Live-Verkehr, Vorlagen und Export der
   Sicherheitseinstellungen. Server: api/aktionen/schutz.php, api/lib/firewall.php.
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, api, esc, icon, toast, confirmBox, dateTime, plural, fmtInt } = W;

  const FILTER = [['', 'Alle'], ['gesperrt', 'Abgewiesen'], ['anmeldung', 'Anmeldungen'], ['fehler', 'Fehler']];
  const DAUER = { 10: '10 Minuten', 60: '1 Stunde', 360: '6 Stunden', 1440: '1 Tag', 10080: '7 Tage' };
  const regionName = (() => { try { const d = new Intl.DisplayNames(['de'], { type: 'region' }); return (c) => { try { return d.of(c); } catch (e) { return c; } }; } catch (e) { return (c) => c; } })();
  let data = null, filter = '', timer = null, letzte = 0;
  /* Einträge haben nur Sekunden: neue Einträge derselben Sekunde wie der letzte angezeigte gingen sonst verloren.
     Daher ab dieser Sekunde nachfragen (seit = letzte − 1) und bereits angezeigte Einträge überspringen. */
  const schluessel = (e) => [e.t, e.ip, e.m, e.q, e.st, e.why, e.ua, e.u, e.n || 1].join('\u0001');

  const zeit = (t) => dateTime(new Date(t * 1000).toISOString());
  const uhr = (t) => new Date(t * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  function stCls(e) {
    const w = e.why || '';
    if (/^(Gesperrt|Firewall|Falle)/.test(w) || e.st === 403) return 'bad';
    if (e.st >= 400 || /fehlgeschlagen/.test(w)) return 'warn';
    return 'ok';
  }
  const uaKurz = (ua) => (!ua ? '—' : /bot|crawl|spider|curl|python|go-http|wget|scan/i.test(ua) ? ua.slice(0, 40) : /Mobile|Android|iPhone/.test(ua) ? 'Handy-Browser' : /Windows|Macintosh|Linux/.test(ua) ? 'Computer-Browser' : ua.slice(0, 40));

  function zeileHTML(e) {
    return `<tr class="fw-row ${stCls(e)}"><td class="num-s">${esc(uhr(e.t))}<div class="sub">${esc(new Date(e.t * 1000).toLocaleDateString('de-DE'))}</div></td>
      <td class="mono-s">${esc(e.ip)}${e.cc ? `<div class="sub">${esc(regionName(e.cc))}</div>` : ''}</td>
      <td><span class="fw-st">${e.st || '—'}</span> ${esc(e.why || 'Anfrage')}${e.n > 1 ? ` <span class="sub">(${fmtInt.format(e.n)}×)</span>` : ''}<div class="sub mono-s fw-q">${esc(e.m || '')} ${esc(e.q || '')}</div></td>
      <td class="fw-ua">${esc(uaKurz(e.ua))}${e.u ? `<div class="sub">${esc(e.u)}</div>` : ''}</td>
      <td class="act">${e.ip && e.ip !== data.meineIp ? `<button type="button" class="btn sm" data-fw="sperr-ip" data-ip="${esc(e.ip)}" title="Diese Adresse sperren">${icon('lock')}Sperren</button>` : ''}</td></tr>`;
  }
  function verkehrHTML(list) {
    if (!list.length) return '<p class="sec-empty">Noch keine Einträge. Angezeigt werden abgewiesene und auffällige Anfragen, Anmeldungen und – während eines Mitschnitts – alle Anfragen.</p>';
    return `<table class="etab fwtab fw-verkehr"><thead><tr><th>Zeit</th><th>Adresse</th><th>Vorgang</th><th>Gerät</th><th class="act"><span class="sr-only">Aktion</span></th></tr></thead><tbody id="fw-rows">${list.map(zeileHTML).join('')}</tbody></table>`;
  }
  function sperrHTML(d) {
    const rows = [
      ...d.manuell.map((e) => `<tr><td class="mono-s">${esc(e.ip)}</td><td>von Hand${e.grund ? ' – ' + esc(e.grund) : ''}<div class="sub">${esc(e.von || '')} · ${esc(dateTime(e.t))}</div></td><td class="num-s">${e.bis ? 'bis ' + esc(zeit(e.bis)) : 'dauerhaft'}</td>
        <td class="act"><button type="button" class="btn sm" data-fw="frei" data-ip="${esc(e.ip)}">Freigeben</button></td></tr>`),
      ...d.auto.map((e) => `<tr><td class="mono-s">${esc(e.ip)}</td><td>automatisch – ${esc(e.grund || '')}<div class="sub">${esc(dateTime(e.t))}${e.n > 1 ? ' · ' + e.n + '. Sperre' : ''}</div></td><td class="num-s">bis ${esc(zeit(e.bis))}</td>
        <td class="act"><button type="button" class="btn sm" data-fw="frei" data-ip="${esc(e.ip)}">Freigeben</button></td></tr>`)];
    return rows.length ? `<table class="etab fwtab"><thead><tr><th>Adresse</th><th>Grund</th><th>Dauer</th><th class="act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${rows.join('')}</tbody></table>${d.autoGesamt > d.auto.length ? `<p class="hint">… und ${d.autoGesamt - d.auto.length} weitere automatische Sperren.</p>` : ''}`
      : '<p class="sec-empty">Derzeit ist keine Adresse gesperrt.</p>';
  }

  function render() {
    const d = data, F = d.fw, Z = d.zahlen;
    const host = $('#view-schutz');
    const feed = d.feed ? `${fmtInt.format(d.feed.anzahl)} Netze · Stand ${esc(dateTime(d.feed.stand))}` : 'noch nicht geladen';
    host.innerHTML = `
      <div class="sec-grid">
        <div class="sec-card ${F.waf === 'sperren' ? 'ok' : F.waf === 'protokoll' ? 'warn' : 'bad'}"><span class="sec-dot"></span><div><strong>Firewall</strong><span>${esc(d.modi[F.waf] || F.waf)}</span><em>${F.autoSperre ? `sperrt nach ${F.treffer} Treffer${F.treffer === 1 ? '' : 'n'} für ${esc(DAUER[F.sperrMinuten] || F.sperrMinuten + ' Min.')}` : 'automatische Sperre aus'}</em></div></div>
        <div class="sec-card ${Z.angriffe ? 'warn' : 'ok'}"><span class="sec-dot"></span><div><strong>${fmtInt.format(Z.angriffe)} Angriffsversuche</strong><span>in den letzten 24 Stunden</span><em>${fmtInt.format(Z.abgewiesen)} Anfragen gesperrter Adressen abgewiesen</em></div></div>
        <div class="sec-card ${Z.gesperrteAdressen ? 'warn' : 'ok'}"><span class="sec-dot"></span><div><strong>${plural(Z.gesperrteAdressen, 'gesperrte Adresse', 'gesperrte Adressen')}</strong><span>von Hand und automatisch</span><em>${fmtInt.format(Z.anmeldungFehl)} fehlgeschlagene Anmeldungen (24 h)</em></div></div>
        <div class="sec-card ${F.feed && d.feed ? 'ok' : 'warn'}"><span class="sec-dot"></span><div><strong>Bedrohungsliste</strong><span>${F.feed ? 'aktiv' : 'aus'}</span><em>${feed}</em></div></div>
      </div>
      <section class="gcard sec-block"><div class="fw-head"><h3 class="sec-h">Live-Verkehr</h3>
        <div class="fw-tools"><div class="fw-filter" role="group" aria-label="Filter">${FILTER.map(([k, l]) => `<button type="button" class="btn sm${filter === k ? ' on' : ''}" data-fw-filter="${k}" aria-pressed="${filter === k}">${l}</button>`).join('')}</div>
          <span class="fw-live" aria-live="polite">${d.mitschnitt ? `${icon('eye')}Mitschnitt aller Anfragen bis ${esc(uhr(d.mitschnitt))}` : 'aktualisiert alle 5 Sekunden'}</span></div></div>
        <div id="fw-verkehr">${verkehrHTML(d.verkehr)}</div>
        <p class="hint">Ihre Adresse: <span class="mono-s">${esc(d.meineIp)}</span>. Interne und freigegebene Adressen werden nie gesperrt.</p>
      </section>
      <section class="gcard sec-block"><h3 class="sec-h">Gesperrte Adressen</h3>
        ${sperrHTML(d)}
        <form class="fw-add" id="fw-add" autocomplete="off">
          <label class="fld"><span>Adresse oder Bereich</span><input name="ip" class="mono-s" placeholder="203.0.113.7 oder 203.0.113.0/24" required maxlength="49"></label>
          <label class="fld"><span>Dauer</span><select name="minuten"><option value="0">dauerhaft</option>${Object.entries(DAUER).map(([v, l]) => `<option value="${v}"${v === '1440' ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
          <label class="fld fw-grund"><span>Grund <small>(optional)</small></span><input name="grund" maxlength="80"></label>
          <button type="submit" class="btn">${icon('lock')}Sperren</button>
        </form>
        <p class="form-err" id="fw-add-err" role="alert"></p>
      </section>
      <form class="gcard sec-form" id="fw-form" autocomplete="off">
        <h3 class="sec-h">Firewall und automatische Sperre</h3>
        <div class="sec-rows">
          <label class="fld"><span>Angriffsmuster in Anfragen</span><select name="waf">${Object.entries(d.modi).map(([k, l]) => `<option value="${k}"${F.waf === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>
            <small>Erkennt eingeschleuste Befehle (SQL, Skripte, Pfade, Code) und bekannte Angriffswerkzeuge. Anfragen angemeldeter Mitarbeiter werden nur in der Adresse geprüft.</small></label>
          <div class="fld"><span>Automatisch sperren</span><div class="sec-inline"><label class="check"><input type="checkbox" name="autoSperre"${F.autoSperre ? ' checked' : ''}> nach</label>
            <label><input type="number" name="treffer" min="1" max="50" value="${F.treffer}"> Treffern in 10 Minuten</label>
            <label>für <select name="sperrMinuten">${d.sperrMinuten.map((v) => `<option value="${v}"${F.sperrMinuten === v ? ' selected' : ''}>${esc(DAUER[v] || v + ' Min.')}</option>`).join('')}</select></label></div>
            <small>Treffer: Angriffsmuster und Zugriffe auf typische Angriffsziele (z. B. /wp-login.php, /.env).</small></div>
          <div class="fld"><span>Fehlerbremse</span><div class="sec-inline"><label>sperren ab <input type="number" name="fehlerLimit" min="0" max="500" value="${F.fehlerLimit}"> fehlerhaften Anfragen in 5 Minuten</label></div>
            <small>0 = aus. Zählt unbekannte Aktionen und ungültige Anfragen ohne Anmeldung (Durchprobieren von Adressen).</small></div>
          <div class="fld"><span>Bedrohungsliste</span><label class="check"><input type="checkbox" name="feed"${F.feed ? ' checked' : ''}> Adressen aus der Spamhaus-DROP-Liste sperren</label>
            <small>Von Kriminellen übernommene Netze; wird täglich beim Öffnen dieser Ansicht aktualisiert (Verbindung zu spamhaus.org). ${feed}.</small>
            <div><button type="button" class="btn sm" data-fw="feed">${icon('download')}Jetzt aktualisieren</button></div></div>
          <label class="fld span2"><span>Nie sperren <small>(eine Adresse oder ein Bereich je Zeile)</small></span><textarea name="erlaubt" rows="2" placeholder="z. B. Büro: 80.147.24.0/24">${esc((F.erlaubt || []).join('\n'))}</textarea>
            <small>Zusätzlich zu den freigegebenen Adressen des Eingabebereichs (Sicherheit).</small></label>
          <label class="fld"><span>Mitschnitt aller Anfragen</span><select name="mitschnittMinuten"><option value="">${d.mitschnitt ? 'läuft bis ' + esc(uhr(d.mitschnitt)) : 'aus'}</option><option value="15">15 Minuten starten</option><option value="60">60 Minuten starten</option>${d.mitschnitt ? '<option value="0">beenden</option>' : ''}</select>
            <small>Zur Fehlersuche: zeigt kurzzeitig jede Anfrage im Live-Verkehr.</small></label>
        </div>
        <div class="sec-foot"><button type="submit" class="btn primary">${icon('check')}Speichern</button></div>
        <p class="form-err" id="fw-err" role="alert"></p>
      </form>
      <section class="gcard sec-block"><h3 class="sec-h">Vorlagen und Sicherung der Einstellungen</h3>
        <div class="fw-vorlagen">${Object.entries(d.vorlagen).map(([k, v]) => `<div class="fw-vorlage"><strong>${esc(v.label)}</strong><p>${esc(v.text)}</p><button type="button" class="btn sm" data-fw="vorlage" data-v="${k}">Anwenden</button></div>`).join('')}</div>
        <p class="hint">Vorlagen ändern Firewall und Sicherheitseinstellungen (Zwei-Faktor-Pflicht, Passwörter, Sitzungsdauer, Kontosperre) – nicht die Listen der freigegebenen Adressen und Länder.</p>
        <div class="fw-io"><button type="button" class="btn" data-fw="export">${icon('download')}Einstellungen exportieren</button>
          <label class="btn">${icon('upload')}Einstellungen importieren<input type="file" accept="application/json,.json" id="fw-import" hidden></label></div>
        <p class="form-err" id="fw-io-err" role="alert"></p>
      </section>`;
    letzte = d.verkehr.length ? d.verkehr[0].t : Math.floor(Date.now() / 1000);
  }

  async function laden() {
    const host = $('#view-schutz');
    if (!data) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Schutz wird geladen …</div>';
    try { data = await api('fw_status', { query: filter ? '&filter=' + filter : '' }); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    render();
    starten();
  }
  /* Live: alle 5 Sekunden neue Einträge holen, solange die Ansicht sichtbar ist */
  function starten() {
    clearInterval(timer);
    timer = setInterval(async () => {
      const v = $('#view-schutz');
      if (!v || v.hidden || document.hidden) { if (v && v.hidden) clearInterval(timer); return; }
      try {
        const r = await api('fw_verkehr', { query: `&seit=${Math.max(0, letzte - 1)}${filter ? '&filter=' + filter : ''}` });
        const gesehen = new Set(data.verkehr.map(schluessel));
        const neu = r.verkehr.filter((e) => !gesehen.has(schluessel(e)));
        if (!neu.length) return;
        letzte = Math.max(letzte, neu[0].t);
        data.verkehr = [...neu, ...data.verkehr].slice(0, 200);
        $('#fw-verkehr').innerHTML = verkehrHTML(data.verkehr);
      } catch { /* nächster Versuch */ }
    }, 5000);
  }
  function fehler(id, ex) { const el = $('#' + id); if (el) el.textContent = ex.message; }
  function uebernehmen(r) { if (r) { data = { ...data, ...r }; render(); } }

  document.addEventListener('click', async (e) => {
    const view = $('#view-schutz');
    if (!view || view.hidden) return;
    const f = e.target.closest('[data-fw-filter]');
    if (f) { filter = f.dataset.fwFilter; laden(); return; }
    const b = e.target.closest('[data-fw]');
    if (!b) return;
    const a = b.dataset.fw;
    try {
      if (a === 'frei') {
        if (!(await confirmBox('Sperre aufheben?', `Die Adresse <span class="mono-s">${esc(b.dataset.ip)}</span> kann danach wieder zugreifen.`, 'Freigeben'))) return;
        uebernehmen(await api('fw_freigeben', { body: { ip: b.dataset.ip } })); toast('Sperre aufgehoben.');
      }
      if (a === 'sperr-ip') {
        if (!(await confirmBox('Adresse sperren?', `<span class="mono-s">${esc(b.dataset.ip)}</span> wird für einen Tag gesperrt (Eingabebereich, Angebotsseite und App).`, 'Sperren', true))) return;
        uebernehmen(await api('fw_sperren', { body: { ip: b.dataset.ip, minuten: 1440, grund: 'aus dem Live-Verkehr' } })); toast('Adresse gesperrt.');
      }
      if (a === 'feed') { b.disabled = true; toast('Bedrohungsliste wird geladen …'); uebernehmen(await api('fw_feed_update', { body: {} })); toast('Bedrohungsliste aktualisiert.'); }
      if (a === 'vorlage') {
        const v = data.vorlagen[b.dataset.v];
        if (!(await confirmBox(`Vorlage „${esc(v.label)}“ anwenden?`, esc(v.text), 'Anwenden'))) return;
        uebernehmen(await api('fw_vorlage', { body: { vorlage: b.dataset.v } })); toast(`Vorlage „${v.label}“ angewendet.`);
      }
      if (a === 'export') {
        const r = await api('fw_export');
        const url = URL.createObjectURL(new Blob([JSON.stringify(r.export, null, 2)], { type: 'application/json' }));
        const link = Object.assign(document.createElement('a'), { href: url, download: `sicherheitseinstellungen-${new Date().toISOString().slice(0, 10)}.json` });
        document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
      }
    } catch (ex) { toast(ex.message, 6000); fehler(a === 'export' ? 'fw-io-err' : 'fw-err', ex); } finally { b.disabled = false; }
  });
  document.addEventListener('submit', async (e) => {
    if (e.target.id === 'fw-add') {
      e.preventDefault();
      const fd = new FormData(e.target);
      try { uebernehmen(await api('fw_sperren', { body: { ip: fd.get('ip').trim(), minuten: +fd.get('minuten'), grund: fd.get('grund') } })); toast('Adresse gesperrt.'); }
      catch (ex) { fehler('fw-add-err', ex); }
    }
    if (e.target.id === 'fw-form') {
      e.preventDefault();
      const fd = new FormData(e.target);
      const body = { waf: fd.get('waf'), autoSperre: fd.get('autoSperre') === 'on', treffer: +fd.get('treffer'), sperrMinuten: +fd.get('sperrMinuten'), fehlerLimit: +fd.get('fehlerLimit'),
        feed: fd.get('feed') === 'on', erlaubt: String(fd.get('erlaubt') || '').split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean) };
      if (fd.get('mitschnittMinuten') !== '') body.mitschnittMinuten = +fd.get('mitschnittMinuten');
      try { uebernehmen(await api('fw_save', { body })); toast('Gespeichert.'); }
      catch (ex) { fehler('fw-err', ex); }
    }
  });
  document.addEventListener('change', async (e) => {
    if (e.target.id !== 'fw-import' || !e.target.files.length) return;
    try {
      const x = JSON.parse(await e.target.files[0].text());
      if (!(await confirmBox('Einstellungen importieren?', 'Firewall und Sicherheitseinstellungen werden aus der Datei übernommen (Listen der Adressen und Länder bleiben).', 'Importieren'))) return;
      uebernehmen(await api('fw_import', { body: { export: x } })); toast('Einstellungen übernommen.');
    } catch (ex) { fehler('fw-io-err', ex.name === 'SyntaxError' ? new Error('Die Datei ist keine gültige JSON-Datei.') : ex); }
    finally { e.target.value = ''; }
  });

  W.views.schutz = laden;
})();
