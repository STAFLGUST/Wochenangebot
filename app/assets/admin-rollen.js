/* ==========================================================================
   Wochenangebot – Eingabebereich, Verwaltung → Rollen und Rechte (nur Administratoren)
   Eigene Rollen anlegen, umbenennen, kopieren und löschen; je Rolle und Modul eine Stufe (Kein Zugang · Ansehen ·
   Bearbeiten · Voll), sensible Rechte einzeln, Vorschau-Bilder wichtiger Rechte (admin-rollen-vorschau.js), dazu
   „Rollen vergleichen“ (alle Rollen nebeneinander, „Was darf …?“ je Mitarbeiter). Die Stufen sind nur Darstellung:
   gespeichert wird wie bisher die Liste der Rechte (rolle_save, rolle_loeschen); der Server ergänzt Voraussetzungen und
   setzt Rechte und Modulzugang durch (GR-103) – diese Seite zeigt und sammelt nur die Auswahl. Daten: Aktion „rechte“
   (rollen, module, catalog mit stufe/sensibel/vorschau, users mit wirksamen Rechten). Neues Design 02.11.2026.
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, api, esc, icon, toast, confirmBox, dateTime, plural } = W;

  const STUFEN = [['kein', 'Kein', 'Kein Zugang'], ['ansehen', 'Ansehen', 'Ansehen'], ['bearbeiten', 'Bearbeiten', 'Bearbeiten'], ['voll', 'Voll', 'Voll']];
  const STUFE_TEXT = { kein: 'kein Zugang', ansehen: 'Ansehen', bearbeiten: 'Bearbeiten', voll: 'Voll', angepasst: 'Angepasst', nurzugang: 'Nur Zugang' };
  const ABSCHNITTE = [['zugang', 'Zugang', ''], ['ansehen', 'Ansehen', ''], ['bearbeiten', 'Bearbeiten', ''], ['voll', 'Freigeben und verwalten', ''],
    ['sensibel', 'Sensibel – einzeln freigeben', 'Gehört zu keiner Stufe. Nur vergeben, wenn die Aufgabe es wirklich braucht.']];
  const SCHMAL = window.matchMedia('(max-width: 1500px)');   // darunter: Rechte des Moduls direkt unter seiner Zeile (mit Seitenleiste der Verwaltung zu eng für drei Spalten)

  let daten = null;          // Antwort von „rechte“
  let wahl = 'editor';       // gewählte Rolle (id) oder '' für eine neue
  let entwurf = null;        // { id, name, beschreibung, rechte:Set, art } – ungespeicherte Auswahl
  let original = null;       // gespeicherter Stand der gewählten Rolle (null = neue Rolle)
  let modulWahl = '';        // Modul in den Details ('' = erstes passendes, '-' = schmal: alle zugeklappt)
  let offen = '';            // Recht mit geöffneter Vorschau
  let ansicht = 'rolle';     // 'rolle' | 'vergleich'
  let filter = 'alle';       // Modulliste: alle | mit | ohne (Zugang)
  let person = '';           // „Was darf …?“: Mitarbeiter-ID

  const kat = () => daten.catalog;
  const recht = (k) => kat().find((p) => p.key === k) || { requires: [] };
  const rolle = (id) => daten.rollen.find((r) => r.id === id);
  /* Voraussetzungen (bearbeiten setzt sehen voraus) – wie rights_close auf dem Server */
  const mitVoraussetzungen = (set) => { let neu = true; while (neu) { neu = false; for (const k of [...set]) for (const r of recht(k).requires) if (!set.has(r)) { set.add(r); neu = true; } } return set; };
  const abhaengige = (k) => kat().filter((p) => p.requires.includes(k)).map((p) => p.key);
  const hinzu = (set, k) => { for (const q of mitVoraussetzungen(new Set([k]))) set.add(q); };
  const entfernen = (set, k) => {
    if (!set.has(k)) return;
    set.delete(k);
    const stapel = [k];
    while (stapel.length) for (const d of abhaengige(stapel.pop())) if (set.has(d)) { set.delete(d); stapel.push(d); }
  };

  /* ---------- Module und Stufen ---------- */
  const rechteVon = (mid) => kat().filter((p) => p.modul === mid);
  const zugangKey = (mid) => (kat().some((p) => p.key === mid + '.zugang') ? mid + '.zugang' : '');
  const module = () => daten.module.filter((m) => rechteVon(m.id).length);
  const stufeDa = (mid, st) => {
    const hat = (s) => rechteVon(mid).some((p) => p.stufe === s);
    return st === 'kein' || (st === 'ansehen' && (hat('ansehen') || !hat('bearbeiten'))) || (st === 'bearbeiten' && hat('bearbeiten')) || (st === 'voll' && hat('voll'));
  };
  const inStufe = (p, st) => st !== 'kein' && (p.stufe === 'zugang' || p.stufe === 'ansehen'
    || (p.stufe === 'bearbeiten' && (st === 'bearbeiten' || st === 'voll')) || (p.stufe === 'voll' && st === 'voll'));
  /* Stufe eines Moduls aus einer Rechteliste; „angepasst“, wenn sie keiner Stufe entspricht (sensible Rechte zählen nicht),
     „nurzugang“, wenn nur die Kachel offen ist (häufig bei Standardrollen: Zugang zu allen Modulen, darin keine Rechte) */
  function stufeVon(set, mid) {
    const norm = rechteVon(mid).filter((p) => p.stufe !== 'sensibel');
    for (const [st] of STUFEN) if (stufeDa(mid, st) && norm.every((p) => inStufe(p, st) === set.has(p.key))) return st;
    const zk = zugangKey(mid);
    return zk && set.has(zk) && norm.every((p) => p.key === zk || !set.has(p.key)) ? 'nurzugang' : 'angepasst';
  }
  function stufeSetzen(mid, st) {
    const set = entwurf.rechte;
    for (const p of rechteVon(mid)) if (p.stufe === 'sensibel' ? st === 'kein' : !inStufe(p, st)) entfernen(set, p.key);
    for (const p of rechteVon(mid)) if (p.stufe !== 'sensibel' && inStufe(p, st)) hinzu(set, p.key);
  }
  const zaehlen = (set, mid) => {
    const r = rechteVon(mid);
    const norm = r.filter((p) => p.stufe !== 'sensibel');
    const sens = r.filter((p) => p.stufe === 'sensibel');
    return { an: norm.filter((p) => set.has(p.key)).length, von: norm.length, sens: sens.length, sensAn: sens.filter((p) => set.has(p.key)).length };
  };
  const symbol = (m) => W.rollenSymbol(m.icon);
  const ico = (m, cls = '') => { const s = symbol(m); return `<span class="rl-ico ${cls}" style="--f:${s.farbe}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${s.pfad}"/></svg></span>`; };
  const rechteSet = (r) => new Set(r.art === 'fest' ? kat().map((p) => p.key) : r.rechte);

  /* ---------- Entwurf ---------- */
  function neuerEntwurf(id, kopie) {
    const r = id ? rolle(id) : null;
    const q = kopie ? rolle(kopie) : null;
    entwurf = r ? { id: r.id, name: r.name, beschreibung: r.beschreibung || '', rechte: rechteSet(r), art: r.art }
      : { id: '', name: q ? `${q.name} (Kopie)` : '', beschreibung: q && q.art === 'eigen' ? q.beschreibung : '',
        // neue Rolle: Rechte mit „Standard an auch in eigenen Rollen“ vorgewählt (z. B. CRM: Umsätze in €, Mengen in kg)
        rechte: q ? rechteSet(q) : new Set(kat().filter((p) => p.eigene).map((p) => p.key)), art: 'eigen' };
    original = r ? { name: entwurf.name, beschreibung: entwurf.beschreibung, rechte: new Set(entwurf.rechte) } : null;
    offen = '';
  }
  function aenderungen() {
    if (!original) return 1;
    let n = 0;
    for (const k of entwurf.rechte) if (!original.rechte.has(k)) n++;
    for (const k of original.rechte) if (!entwurf.rechte.has(k)) n++;
    if (entwurf.name !== original.name) n++;
    if (entwurf.beschreibung !== original.beschreibung) n++;
    return n;
  }
  const geaendert = () => entwurf && entwurf.art !== 'fest' && aenderungen() > 0;
  const standText = () => (entwurf.art === 'fest' ? 'Feste Rolle – nicht änderbar'
    : !original ? 'Neue Rolle – noch nicht gespeichert'
      : aenderungen() ? `${plural(aenderungen(), 'Änderung', 'Änderungen')} noch nicht gespeichert` : 'Alles gespeichert');

  /* ---------- Bausteine ---------- */
  function stufenHTML(m, gross) {
    const st = stufeVon(entwurf.rechte, m.id);
    const fest = entwurf.art === 'fest';
    return `<div class="rl-stufen${gross ? ' gross' : ''}" role="group" aria-label="Stufe für ${esc(m.name)}">${STUFEN.map(([id, kurz, lang]) => (stufeDa(m.id, id)
      ? `<button type="button" data-rl-stufe="${esc(m.id)}:${id}" data-ort="${gross ? 'd' : 'z'}" data-st="${id}" aria-pressed="${st === id}"${fest ? ' disabled' : ''}${gross ? '' : ` aria-label="${esc(lang)}"`}><i aria-hidden="true"></i>${gross ? lang : kurz}</button>`
      : '<span class="rl-st-leer" aria-hidden="true">–</span>')).join('')}</div>`;
  }

  function listeHTML() {
    const gruppen = [['fest', 'Feste Rolle'], ['standard', 'Standardrollen'], ['eigen', 'Eigene Rollen']];
    return gruppen.map(([art, titel]) => {
      const rl = daten.rollen.filter((r) => r.art === art);
      if (!rl.length) return '';
      return `<span class="rl-gruppe">${titel}</span>` + rl.map((r) => {
        const set = r.id === wahl ? entwurf.rechte : rechteSet(r);
        const mods = module().filter((m) => zugangKey(m.id) && set.has(zugangKey(m.id)));
        const anders = r.id === wahl && geaendert();
        return `<button type="button" class="rl-item${r.id === wahl ? ' on' : ''}" data-rl-wahl="${esc(r.id)}" aria-pressed="${r.id === wahl}">
          <span class="rl-item-n">${esc(r.name)}${r.art === 'fest' ? icon('lock', 'sm') : ''}${anders ? '<span class="rl-tag rl-neu">geändert</span>' : ''}</span>
          <span class="rl-item-m">${plural(r.mitarbeiter, 'Mitarbeiter', 'Mitarbeiter')} · ${r.art === 'fest' ? 'alle Module' : plural(mods.length, 'Modul', 'Module')}</span>
          <span class="rl-dots" aria-hidden="true">${mods.map((m) => `<i style="--f:${symbol(m).farbe}"></i>`).join('')}</span></button>`;
      }).join('');
    }).join('') + (wahl === '' ? `<button type="button" class="rl-item on" aria-pressed="true"><span class="rl-item-n">${esc(entwurf.name || 'Neue Rolle')}</span><span class="rl-item-m">noch nicht gespeichert</span></button>` : '')
      + `<div class="rl-liste-hinw">Ein Mitarbeiter kann mehrere Rollen haben – es gilt die Summe. Ausnahmen für einzelne Mitarbeiter stehen unter „Mitarbeiter“.
        <button type="button" class="rl-link" data-rl-akt="vergleich">Alle Rollen vergleichen</button></div>`;
  }

  function kopfHTML() {
    const r = entwurf.id ? rolle(entwurf.id) : null;
    const fest = entwurf.art === 'fest';
    const eigen = entwurf.art === 'eigen';
    const leute = r ? (daten.users || []).filter((u) => u.active && (u.rollen || []).includes(r.id)) : [];
    const ini = (n) => n.split(/[\s.]+/).filter(Boolean).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
    return `<section class="gcard rl-kopf" aria-label="Rolle">
      <div class="rl-kopf-t">
        <div class="rl-felder">
          <label class="fld"><span>Name der Rolle</span><input id="rl-name" maxlength="40" value="${esc(entwurf.name)}"${fest ? ' disabled' : ''} placeholder="z. B. Vertrieb, Lager, Personalstelle" autocomplete="off"></label>
          ${eigen ? `<label class="fld"><span>Beschreibung <small class="muted">(optional)</small></span><input id="rl-besch" maxlength="160" value="${esc(entwurf.beschreibung)}" placeholder="Wofür ist die Rolle gedacht?" autocomplete="off"></label>`
            : `<p class="hint rl-art">${fest ? 'Administratoren haben immer alle Rechte, dazu die Verwaltung von Mitarbeitern, Rollen, Sicherheit und E-Mail. Diese Rolle ist fest.' : 'Standardrolle: Name und Rechte sind änderbar, die Rolle selbst bleibt bestehen.'}</p>`}
        </div>
        ${r ? `<div class="rl-leute">${leute.slice(0, 6).map((u) => `<span class="rl-person"><i aria-hidden="true">${esc(ini(u.name))}</i>${esc(u.name)}</span>`).join('')}
          ${leute.length > 6 ? `<span>+ ${leute.length - 6} weitere</span>` : ''}${!leute.length ? '<span>Noch keinem Mitarbeiter zugeordnet.</span>' : ''}
          <button type="button" class="rl-link" data-rl-akt="mitarbeiter">Unter „Mitarbeiter“ zuordnen</button></div>
          <p class="rl-meta">${plural(r.mitarbeiter, 'Mitarbeiter hat', 'Mitarbeiter haben')} diese Rolle${r.geaendert ? ` · geändert ${esc(dateTime(r.geaendert))}${r.geaendertVon ? ' von ' + esc(r.geaendertVon) : ''}` : ''}</p>` : ''}
      </div>
      ${r ? `<div class="rl-det-akt">
        <button type="button" class="btn sm" data-rl-akt="kopie">${icon('copy', 'sm')}Als neue Rolle kopieren</button>
        ${eigen ? `<button type="button" class="btn sm ghost rl-loeschen" data-rl-akt="loeschen">${icon('trash', 'sm')}Rolle löschen</button>` : ''}
        ${entwurf.art === 'standard' ? `<button type="button" class="btn sm ghost" data-rl-akt="standard">${icon('undo', 'sm')}Standard wiederherstellen</button>` : ''}
      </div>` : ''}
      <p class="form-err" id="rl-err" role="alert"></p>
    </section>`;
  }

  function blickHTML(aktiv) {
    const set = entwurf.rechte;
    const kacheln = module().filter((m) => zugangKey(m.id));
    const mit = kacheln.filter((m) => set.has(zugangKey(m.id))).length;
    const sens = kat().filter((p) => p.stufe === 'sensibel' && set.has(p.key)).length;
    return `<section class="gcard rl-blick" aria-labelledby="rl-blick-t">
      <div class="rl-blick-k"><h3 id="rl-blick-t">Auf einen Blick: das Dashboard dieser Rolle</h3>
        <span class="rl-zahlen"><span><b>${mit}</b> von ${kacheln.length} Modulen</span><span><b>${set.size}</b> Rechte</span><span><b class="${sens ? 'rot' : ''}">${sens}</b> sensibel</span></span></div>
      <div class="rl-kacheln">${kacheln.map((m) => {
        const st = stufeVon(set, m.id);
        const an = set.has(zugangKey(m.id));
        const text = an ? STUFE_TEXT[st] : 'kein Zugang';
        return `<button type="button" class="rl-kachel${m.id === aktiv ? ' on' : ''}" data-rl-oeffnen="${esc(m.id)}" aria-label="${esc(m.name)}: ${esc(text)} – Rechte anzeigen">
          ${ico(m, an ? '' : 'aus')}<span class="rl-kachel-n">${esc(m.name)}</span><span class="rl-kachel-s st-${an ? st : 'kein'}">${esc(text)}</span></button>`;
      }).join('')}</div></section>`;
  }

  function zeilenHTML(aktiv) {
    const set = entwurf.rechte;
    const liste = module().filter((m) => { const z = zugangKey(m.id); const an = !z || set.has(z); return filter === 'alle' || (filter === 'mit' ? an : !an); });
    const mitZ = module().filter((m) => !zugangKey(m.id) || set.has(zugangKey(m.id))).length;
    const schmal = SCHMAL.matches;
    const f = (id, l) => `<button type="button" data-rl-filter="${id}" aria-pressed="${filter === id}">${l}</button>`;
    return `<section class="rl-mods" aria-labelledby="rl-mods-t">
      <div class="rl-mods-k"><h3 id="rl-mods-t">Module und Stufen</h3>
        <div class="rl-filter" role="group" aria-label="Module filtern">${f('alle', `Alle ${module().length}`)}${f('mit', `Mit Zugang ${mitZ}`)}${f('ohne', `Ohne Zugang ${module().length - mitZ}`)}</div></div>
      <p class="rl-legende">Ansehen = nur lesen · Bearbeiten = auch ändern, hochladen, senden · Voll = zusätzlich freigeben, verwalten, löschen. Sensible Rechte ${icon('lock', 'sm')} gehören zu keiner Stufe.</p>
      <ul class="rl-zeilen">${liste.map((m) => {
        const st = stufeVon(set, m.id);
        const z = zaehlen(set, m.id);
        const on = m.id === aktiv;
        const status = m.kachel && !m.freigegeben ? ' <span class="rl-tag rl-plan">in Vorbereitung</span>' : '';
        return `<li class="rl-zeile${on ? ' on' : ''}" data-rl-modul="${esc(m.id)}">
          <button type="button" class="rl-z-kopf" data-rl-oeffnen="${esc(m.id)}"${schmal ? ` aria-expanded="${on}"` : ''} aria-label="${esc(m.name)} – Rechte ${schmal && on ? 'zuklappen' : 'anzeigen'}">
            ${ico(m)}<span class="rl-z-t"><b>${esc(m.name)}${status}</b><small>${esc(m.beschreibung)}</small></span></button>
          ${stufenHTML(m, false)}
          <div class="rl-z-info">${st === 'angepasst' || st === 'nurzugang' ? `<span class="rl-chip angepasst">${STUFE_TEXT[st]}</span>` : ''}
            <span>${z.an ? `${z.an} von ${plural(z.von, 'Recht', 'Rechten')}` : 'kein Recht'}</span>
            ${z.sens ? `<span class="rl-chip${z.sensAn ? ' sens-an' : ''}">${icon('lock', 'sm')}${z.sensAn ? `${z.sensAn} sensibel an` : (z.sens === 1 ? 'sensibel aus' : `${z.sens} sensibel aus`)}</span>` : ''}</div>
        </li>${schmal && on ? `<li class="rl-zeile-det" id="rl-detail" aria-labelledby="rl-det-t">${detailHTML(m)}</li>` : ''}`;
      }).join('') || '<li class="rl-zeile rl-leer">Keine Module in dieser Auswahl.</li>'}</ul>
      <div class="rl-admin"><h4>${icon('lock', 'sm')}Nur Administratoren – nicht vergebbar</h4>
        <p>Fest vorbehalten, damit sich niemand selbst höhere Rechte geben kann.</p>
        <div class="rl-admin-l">${daten.adminOnly.map((l) => `<span>${esc(l)}</span>`).join('')}</div></div>
    </section>`;
  }

  /* Ein Recht: Schalter, Bezeichnung, Erklärung (falls im Katalog), Voraussetzung, Vorschau-Bild */
  function rechtHTML(p, m) {
    const fest = entwurf.art === 'fest';
    const an = entwurf.rechte.has(p.key);
    const voraus = (p.requires || []).map((k) => recht(k)).filter((r) => r.label && r.kind !== 'zugang').map((r) => `„${r.label}“`);
    const bild = p.vorschau ? W.rollenVorschau(p.vorschau, m.name, m.icon) : '';
    const auf = bild && offen === p.key;
    return `<div class="rl-r${an ? ' an' : ''}" data-rl-recht="${esc(p.key)}">
      <div class="rl-r-k"><label class="rl-sw"><input type="checkbox" role="switch" data-rl-key="${esc(p.key)}"${an ? ' checked' : ''}${fest ? ' disabled' : ''}>
        <span class="rl-r-t"><span>${esc(p.label)}</span>${p.hilfe ? `<small class="rl-hilfe">${esc(p.hilfe)}</small>` : ''}${p.hilfe && voraus.length ? `<small class="rl-voraus">Setzt ${esc(voraus.join(' und '))} voraus – wird mit eingeschaltet.</small>` : ''}</span></label>
        ${bild ? `<button type="button" class="rl-vbtn" data-rl-vorschau="${esc(p.key)}" aria-expanded="${auf}">${icon('eye', 'sm')}${auf ? 'Schließen' : 'Vorschau'}</button>` : ''}</div>
      ${auf ? `<div class="rl-v"><p class="rl-vt${an ? ' an' : ''}">${an ? 'So sieht es der Mitarbeiter mit diesem Recht:' : 'Das käme mit diesem Recht dazu – diese Rolle sieht es derzeit nicht:'}</p>${bild}</div>` : ''}
    </div>`;
  }

  function detailHTML(m) {
    const st = stufeVon(entwurf.rechte, m.id);
    const z = zaehlen(entwurf.rechte, m.id);
    const teil = m.teil_von ? (daten.module.find((x) => x.id === m.teil_von) || {}).name : '';
    const zk = zugangKey(m.id);
    let erkl = zk && !entwurf.rechte.has(zk) ? 'Ohne Zugang erscheint die Kachel nicht und die Oberfläche des Moduls ist gesperrt.'
      : st === 'angepasst' ? `Angepasst: ${z.an} von ${plural(z.von, 'Recht', 'Rechten')}, abweichend von den Stufen.`
        : st === 'nurzugang' ? 'Nur Zugang: Die Kachel erscheint und das Modul lässt sich öffnen, Rechte darin hat die Rolle keine.'
        : st === 'kein' ? 'Diese Rolle hat in diesem Modul keine Rechte.' : `Stufe „${STUFE_TEXT[st]}“: ${z.an} von ${plural(z.von, 'Recht', 'Rechten')}.`;
    if (zk && !entwurf.rechte.has(zk) && z.an) erkl += ' Eingeschaltete Rechte gelten nur dort, wo andere Module sie nutzen.';
    if (z.sens) erkl += ' Sensible Rechte werden zusätzlich einzeln freigegeben.';
    const abschnitte = ABSCHNITTE.map(([s, titel, hinweis]) => {
      const liste = rechteVon(m.id).filter((p) => p.stufe === s);
      if (!liste.length) return '';
      return `<div class="rl-abschn${s === 'sensibel' ? ' sens' : ''}"><h4>${s === 'sensibel' ? icon('lock', 'sm') : ''}${titel}</h4>${hinweis ? `<p>${hinweis}</p>` : ''}
        <div class="rl-rl">${liste.map((p) => rechtHTML(p, m)).join('')}</div></div>`;
    }).join('');
    return `<div class="rl-det-k">
        <div class="rl-det-t">${ico(m, 'gross')}<div><span class="rl-ober">Rechte im Modul</span><h3 id="rl-det-t">${esc(m.name)}${m.kachel && !m.freigegeben ? ' <span class="rl-tag rl-plan">in Vorbereitung</span>' : ''}</h3>
          <p>${esc(m.beschreibung)}${teil ? ` · öffnet die Importzentrale im Bereich „${esc(teil)}“` : ''}</p></div></div>
        ${stufenHTML(m, true)}
        <p class="rl-erkl">${esc(erkl)}</p>
        ${m.kachel && !m.freigegeben && rechteVon(m.id).length === 1 ? '<p class="rl-erkl">Die Rechte innerhalb des Moduls kommen mit seiner Freigabe hinzu.</p>' : ''}
      </div>
      <div class="rl-det-b">${abschnitte}</div>`;
  }

  /* ---------- Rollen vergleichen ---------- */
  function vergleichHTML() {
    const nutzer = (daten.users || []).filter((u) => u.active);
    if (!nutzer.some((u) => u.id === person)) person = (nutzer.find((u) => u.role !== 'admin') || nutzer[0] || {}).id || '';
    const p = nutzer.find((u) => u.id === person);
    const meine = new Set(p ? (p.rollen || []) : []);
    const mods = module();
    let was = '';
    if (p) {
      const set = new Set(p.perms || []);
      const namen = [...meine].map((id) => `„${(rolle(id) || {}).name || id}“`);
      const bekannt = (k) => !!recht(k).label;
      const ausn = [...(p.grant || []).filter(bekannt).map((k) => ['plus', '+ ' + recht(k).label]), ...(p.deny || []).filter(bekannt).map((k) => ['minus', '− ' + recht(k).label])];
      was = `<p>${esc(p.name)} hat ${namen.length === 1 ? 'die Rolle ' + esc(namen[0]) : 'die Rollen ' + esc(namen.join(' und '))}. Es gilt die Summe der Rollen${ausn.length ? ', dazu persönliche Ausnahmen' : ''}.</p>
        <div class="rl-erg">${mods.map((m) => {
          const z = zugangKey(m.id);
          const st = z && !set.has(z) ? 'kein' : stufeVon(set, m.id);
          const s = zaehlen(set, m.id).sensAn;
          return `<span class="${st === 'kein' ? 'aus' : ''}"><i style="--f:${symbol(m).farbe}"></i><b>${esc(m.name)}</b><em class="st-${st}">${esc(STUFE_TEXT[st])}${s ? ` · ${s} sensibel` : ''}</em></span>`;
        }).join('')}</div>
        ${ausn.length ? `<div class="rl-ausn"><b>Ausnahmen nur für diesen Mitarbeiter:</b>${ausn.map(([k, t]) => `<span class="${k}">${esc(t)}</span>`).join('')}</div>` : ''}`;
    }
    return `<section class="gcard rl-was" aria-labelledby="rl-was-t">
        <div class="rl-was-k"><h3 id="rl-was-t">Was darf …?</h3>
          <label class="fld"><span>Mitarbeiter</span><select id="rl-person">${nutzer.map((u) => `<option value="${esc(u.id)}"${u.id === person ? ' selected' : ''}>${esc(u.name)}</option>`).join('')}</select></label></div>
        ${was || '<p>Noch keine Mitarbeiter angelegt.</p>'}
      </section>
      <section class="gcard rl-mx-box" aria-labelledby="rl-mx-t">
        <div class="rl-mx-k"><h3 id="rl-mx-t">Alle Rollen im Überblick</h3><span>${p ? `Hervorgehoben: die Rollen von ${esc(p.name)}. ` : ''}Ein Klick öffnet das Modul in der Rolle.</span></div>
        <div class="rl-mx-s"><table class="rl-mx"><thead><tr><th scope="col">Modul</th>${daten.rollen.map((r) => `<th scope="col" class="${meine.has(r.id) ? 'mein' : ''}">${esc(r.name)}<small>${r.art === 'fest' ? 'fest' : r.art === 'standard' ? 'Standard' : 'eigene'} · ${plural(r.mitarbeiter, 'MA', 'MA')}</small></th>`).join('')}</tr></thead>
          <tbody>${mods.map((m) => `<tr><th scope="row">${ico(m)}${esc(m.name)}</th>${daten.rollen.map((r) => {
            const set = rechteSet(r);
            const z = zugangKey(m.id);
            const st = r.art === 'fest' ? 'voll' : (z && !set.has(z) ? 'kein' : stufeVon(set, m.id));
            const text = r.art === 'fest' ? 'Alle Rechte' : STUFE_TEXT[st];
            const s = r.art === 'fest' ? 0 : zaehlen(set, m.id).sensAn;
            return `<td class="${meine.has(r.id) ? 'mein' : ''}"><button type="button" class="rl-pill st-${r.art === 'fest' ? 'alle' : st}" data-rl-zelle="${esc(r.id)}|${esc(m.id)}" aria-label="${esc(m.name)}, ${esc(r.name)}: ${esc(text)}${s ? `, ${s} sensibel` : ''} – öffnen"><i aria-hidden="true"></i>${esc(text)}</button>${s ? `<span class="rl-mx-sens">${icon('lock', 'sm')}${s}</span>` : ''}</td>`;
          }).join('')}</tr>`).join('')}</tbody></table></div>
      </section>`;
  }

  /* ---------- Zeichnen ---------- */
  function aktivesModul() {
    if (modulWahl === '-') return SCHMAL.matches ? '' : (module()[0] || {}).id;
    if (modulWahl && module().some((m) => m.id === modulWahl)) return modulWahl;
    if (SCHMAL.matches) return '';
    const mit = module().find((m) => zugangKey(m.id) && entwurf.rechte.has(zugangKey(m.id)));
    return (mit || module()[0] || {}).id;
  }

  function zeichnen() {
    const host = $('#view-rollen');
    const fest = entwurf.art === 'fest';
    const aktiv = aktivesModul();
    const am = module().find((m) => m.id === aktiv);
    const knoepfe = ansicht === 'vergleich'
      ? `<button type="button" class="btn" data-rl-akt="zurueck">${icon('back')}Zurück zur Rolle</button>`
      : `<button type="button" class="btn" data-rl-akt="vergleich">${icon('users')}Rollen vergleichen</button>
        <button type="button" class="btn" data-rl-akt="neu">${icon('plus')}Neue Rolle</button>
        ${fest ? '' : `${entwurf.id ? `<button type="button" class="btn ghost" data-rl-akt="verwerfen"${geaendert() ? '' : ' disabled'}>Verwerfen</button>` : '<button type="button" class="btn ghost" data-rl-akt="verwerfen">Abbrechen</button>'}
        <button type="button" class="btn primary" data-rl-akt="speichern">${icon('check', 'sm')}${entwurf.id ? 'Rolle speichern' : 'Rolle anlegen'}</button>`}`;
    host.innerHTML = `<div class="ed-toolbar rl-tb"><span class="rl-stand${geaendert() ? ' offen' : ''}" id="rl-stand" role="status">${ansicht === 'vergleich' ? `${plural(daten.rollen.length, 'Rolle', 'Rollen')} nebeneinander` : esc(standText())}</span>${knoepfe}</div>
      ${ansicht === 'vergleich' ? `<div class="rl-vergleich">${vergleichHTML()}</div>` : `<div class="rl-layout">
        <nav class="gcard rl-liste" aria-label="Rollen">${listeHTML()}</nav>
        <div class="rl-main">
          ${kopfHTML()}
          ${blickHTML(aktiv)}
          <div class="rl-arbeit">
            ${zeilenHTML(aktiv)}
            ${!SCHMAL.matches && am ? `<aside class="gcard rl-det" id="rl-detail" aria-labelledby="rl-det-t">${detailHTML(am)}</aside>` : ''}
          </div>
        </div>
      </div>`}`;
  }
  /* Neu zeichnen und den Fokus auf dem bedienten Element halten (Tastatur, Bildschirmleser) */
  function neuZeichnen(fokus, ersatz) {
    zeichnen();
    const sichtbar = (sel) => (sel ? [...$('#view-rollen').querySelectorAll(sel)].find((x) => x.offsetParent !== null) : null);
    const el = sichtbar(fokus) || sichtbar(ersatz);   // z. B. Stufe der Zeile ausgeblendet, weil das Modul darunter aufgeklappt ist
    if (el) el.focus({ preventScroll: true });
  }
  function standAktualisieren() {
    const st = $('#rl-stand'); if (st) { st.textContent = standText(); st.classList.toggle('offen', geaendert()); }
    const v = $('#view-rollen [data-rl-akt="verwerfen"]'); if (v && entwurf.id) v.disabled = !geaendert();
    const it = $('#view-rollen .rl-item.on .rl-item-n');
    if (it && entwurf.id) {
      const tag = it.querySelector('.rl-neu');
      if (geaendert() && !tag) it.insertAdjacentHTML('beforeend', '<span class="rl-tag rl-neu">geändert</span>');
      if (!geaendert() && tag) tag.remove();
    }
  }
  async function weiterOhneSpeichern() {
    if (!geaendert()) return true;
    return confirmBox('Änderungen verwerfen?', 'Die Änderungen an dieser Rolle sind noch nicht gespeichert.', 'Verwerfen', true);
  }

  async function laden(id) {
    const host = $('#view-rollen');
    if (!daten) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Rollen werden geladen …</div>';
    try { daten = await api('rechte'); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    if (id !== undefined) wahl = id;
    if (wahl !== '' && !rolle(wahl)) wahl = 'editor';
    if (wahl !== '' || !entwurf) neuerEntwurf(wahl === '' ? null : wahl);
    zeichnen();
  }

  const host = $('#view-rollen');
  SCHMAL.addEventListener('change', () => { if (daten && entwurf && !host.hidden) zeichnen(); });
  host.addEventListener('input', (e) => {
    if (e.target.id === 'rl-name') { entwurf.name = e.target.value; standAktualisieren(); }
    if (e.target.id === 'rl-besch') { entwurf.beschreibung = e.target.value; standAktualisieren(); }
  });
  host.addEventListener('change', (e) => {
    if (e.target.id === 'rl-person') { person = e.target.value; neuZeichnen('#rl-person'); return; }
    const k = e.target.dataset.rlKey;
    if (!k) return;
    if (e.target.checked) hinzu(entwurf.rechte, k); else entfernen(entwurf.rechte, k);
    neuZeichnen(`[data-rl-key="${CSS.escape(k)}"]`);
  });
  host.addEventListener('click', async (e) => {
    const w = e.target.closest('[data-rl-wahl]');
    if (w) {
      if (w.dataset.rlWahl === wahl) return;
      if (!(await weiterOhneSpeichern())) return;
      wahl = w.dataset.rlWahl; neuerEntwurf(wahl); zeichnen();
      if (window.matchMedia('(max-width: 900px)').matches) { const k = $('#view-rollen .rl-kopf'); if (k) k.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
      return;
    }
    const o = e.target.closest('[data-rl-oeffnen]');
    if (o) {
      const mid = o.dataset.rlOeffnen;
      const vonKachel = o.classList.contains('rl-kachel');
      modulWahl = SCHMAL.matches && aktivesModul() === mid && !vonKachel ? '-' : mid;
      offen = '';
      neuZeichnen(`[data-rl-oeffnen="${CSS.escape(mid)}"]${vonKachel ? '.rl-kachel' : '.rl-z-kopf'}`);
      if (vonKachel || SCHMAL.matches) {
        const ziel = SCHMAL.matches ? host.querySelector(`.rl-zeile[data-rl-modul="${CSS.escape(mid)}"]`) : $('#rl-detail');
        if (ziel && vonKachel) ziel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
      return;
    }
    const s = e.target.closest('[data-rl-stufe]');
    if (s) {
      const [mid, st] = s.dataset.rlStufe.split(':');
      stufeSetzen(mid, st);
      if (aktivesModul() !== mid) { modulWahl = mid; offen = ''; }   // Stufe gewählt → Details zeigen dieses Modul
      neuZeichnen(`[data-rl-stufe="${CSS.escape(s.dataset.rlStufe)}"][data-ort="${s.dataset.ort}"]`, `[data-rl-stufe="${CSS.escape(s.dataset.rlStufe)}"]`);
      return;
    }
    const v = e.target.closest('[data-rl-vorschau]');
    if (v) { offen = offen === v.dataset.rlVorschau ? '' : v.dataset.rlVorschau; neuZeichnen(`[data-rl-vorschau="${CSS.escape(v.dataset.rlVorschau)}"]`); return; }
    const f = e.target.closest('[data-rl-filter]');
    if (f) { filter = f.dataset.rlFilter; neuZeichnen(`[data-rl-filter="${filter}"]`); return; }
    const c = e.target.closest('[data-rl-zelle]');
    if (c) {
      const [rid, mid] = c.dataset.rlZelle.split('|');
      if (rid !== wahl && !(await weiterOhneSpeichern())) return;
      if (rid !== wahl) { wahl = rid; neuerEntwurf(rid); }
      ansicht = 'rolle'; modulWahl = mid; filter = 'alle';
      zeichnen();
      const ziel = SCHMAL.matches ? host.querySelector(`.rl-zeile[data-rl-modul="${CSS.escape(mid)}"]`) : $('#rl-detail');
      if (ziel) ziel.scrollIntoView({ block: 'start', behavior: 'smooth' });
      return;
    }
    const a = e.target.closest('[data-rl-akt]')?.dataset.rlAkt;
    if (!a) return;
    if (a === 'vergleich' || a === 'zurueck') { ansicht = a === 'vergleich' ? 'vergleich' : 'rolle'; zeichnen(); window.scrollTo({ top: 0 }); return; }
    if (a === 'mitarbeiter') { const t = $('#vt-users'); if (t) t.click(); return; }
    if (a === 'neu' || a === 'kopie') {
      if (!(await weiterOhneSpeichern())) return;
      const quelle = a === 'kopie' ? entwurf.id : null;
      wahl = ''; ansicht = 'rolle'; neuerEntwurf(null, quelle); zeichnen();
      const n = $('#rl-name'); if (n) { n.focus(); n.select(); }
      return;
    }
    if (a === 'standard') {   // Standardrechte laut Katalog (bisheriges Rollenmodell) – wirksam erst mit „Rolle speichern“
      entwurf.rechte = new Set(kat().filter((p) => p.default.includes(entwurf.id)).map((p) => p.key));
      zeichnen();
      toast('Standard eingetragen – zum Übernehmen „Rolle speichern“.');
      return;
    }
    if (a === 'verwerfen') {
      if (!entwurf.id) { wahl = 'editor'; neuerEntwurf('editor'); zeichnen(); return; }
      neuerEntwurf(entwurf.id); zeichnen(); return;
    }
    if (a === 'loeschen') {
      const r = rolle(entwurf.id);
      if (r.mitarbeiter) { $('#rl-err').textContent = `Die Rolle ist noch ${plural(r.mitarbeiter, 'Mitarbeiter', 'Mitarbeitern')} zugeordnet. Bitte dort zuerst eine andere Rolle wählen.`; return; }
      if (!(await confirmBox('Rolle löschen?', `Die Rolle „${esc(r.name)}“ wird gelöscht. Das lässt sich nicht rückgängig machen.`, 'Löschen', true))) return;
      try { await api('rolle_loeschen', { body: { id: r.id } }); toast(`Rolle „${r.name}“ gelöscht.`); await laden('editor'); }
      catch (ex) { const f2 = $('#rl-err'); if (f2) f2.textContent = ex.message; }
      return;
    }
    if (a === 'speichern') {
      const err = $('#rl-err'); err.textContent = '';
      const name = entwurf.name.trim();
      if (name.length < 2) { err.textContent = 'Bitte einen Namen für die Rolle angeben (mindestens 2 Zeichen).'; $('#rl-name').focus(); return; }
      const btn = e.target.closest('button'); btn.disabled = true;
      try {
        const r = await api('rolle_save', { body: { id: entwurf.id, name, beschreibung: entwurf.beschreibung.trim(), rechte: [...entwurf.rechte] } });
        const neu = !entwurf.id;
        toast(neu ? `Rolle „${name}“ angelegt – jetzt unter „Mitarbeiter“ zuordnen.` : `Rolle „${name}“ gespeichert. Die Rechte gelten ab der nächsten Aktion der Mitarbeiter.`);
        await laden(r.id);
      } catch (ex) { err.textContent = ex.message; btn.disabled = false; }
    }
  });

  W.views.rollen = () => laden();
})();
