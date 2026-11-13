/* Angebot · Satz der Druckfassung „Angebotsansicht“ (A4 quer) für die Angebotsseite (frontend.js, Wunsch des Inhabers 13.11.2026).
   Fortlaufend und kompakt statt „jeder Bereich auf einer neuen Seite“: Bereiche und Gruppen laufen direkt hintereinander
   durch die Spalten und Seiten; eine Gruppe wird nie geteilt, solange sie in eine leere Spalte passt (sonst mit „Forts.“);
   eine Bereichsüberschrift bleibt bei ihrer ersten Gruppe. Die Spalten der letzten Seite werden ausgeglichen; wäre die letzte
   Seite fast leer, werden die letzten beiden Seiten gemeinsam ausgeglichen. Drei oder vier Spalten – genommen wird, was
   weniger Seiten braucht (bei Gleichstand drei, besser lesbar).
   Damit das stimmt, wird nicht geschätzt, sondern gemessen: die Bausteine werden einmal unsichtbar in Druckgröße gesetzt
   (feste mm-/pt-Maße aus angebot-druck.css, unabhängig vom Bildschirm), dann rechnerisch auf Seiten fester Höhe verteilt.
   Jede Seite hat einen schlanken Kopf (Seite x von y); Fußzeile des Briefbogens mit dem Hinweis darüber steht am Seitenfuß
   – auf jeder Seite („jede“) oder nur auf der letzten („letzte“), der Platz dafür ist reserviert (nichts wird überdeckt).
   Kein Zugriff auf Daten: frontend.js liefert fertige HTML-Bausteine (nur aufgelöste Angebotsdaten, GR-001/GR-002).
   Schnittstelle: window.AngebotDruck = { liste(cfg), fussHTML(fuss, hinweis, art) }. */
(function (root) {
  'use strict';
  const SEITE = { b: 279, h: 193 };          // Satzspiegel in mm (A4 quer 297 × 210, Ränder 9 mm seitlich, 8 mm oben/unten, 1 mm Reserve)
  const ABSTAND = { gruppe: 2.6, bereich: 3.4, nachBereich: 1.4, spalteMin: 55 };   // mm, wie in angebot-druck.css
  const MIN_ZEILEN = 3;                       // so viele Zeilen einer geteilten Gruppe stehen mindestens am Spaltenende
  const EPS = 0.5;                            // px Toleranz beim Vergleichen gemessener Höhen
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
  const zeilen = (t) => String(t ?? '').split('\n').map((l) => l.trim()).filter(Boolean);
  const verlinkt = (l) => esc(l);   // bewusst ohne Links: Papier

  /* Fußzeile des Briefbogens: Siegel, drei Textspalten, zwei Zeilen (Handelsregister); darüber der Hinweis (Mengen, Fracht).
     art „quer“: alles in einer Reihe über die Seitenbreite (Zeilen als vierter Block); „hoch“: Zeilen unter den Spalten. */
  function fussHTML(fuss, hinweis, art) {
    const f = fuss || {}, sp = Array.isArray(f.spalten) ? f.spalten : [], ze = (Array.isArray(f.zeilen) ? f.zeilen : []).filter((z) => String(z || '').trim());
    const hin = (hinweis || []).filter((l) => String(l || '').trim());
    const spalten = sp.map((t) => zeilen(t)).filter((l) => l.length);
    if (!spalten.length && !ze.length && !hin.length) return '';
    const brief = spalten.length || ze.length ? `<div class="pl-brief"><img class="pl-siegel" src="assets/druck-siegel.jpg" width="316" height="250" alt="">
        ${spalten.map((l) => `<p class="pl-bs">${l.map(verlinkt).join('<br>')}</p>`).join('')}
        ${ze.length ? `<p class="pl-bz">${ze.map((z) => `<span>${esc(z)}</span>`).join(' ')}</p>` : ''}</div>` : '';
    return `<footer class="pl-fuss pl-fuss-${art === 'hoch' ? 'hoch' : 'quer'}">${hin.length ? `<p class="pl-hinweis">${hin.map((l, i) => `<span${i === 0 ? ' class="lead"' : ''}>${esc(l)}</span>`).join(' ')}</p>`.replace(/([^.!?:;…])<\/span> <span/g, '$1</span> · <span') : ''}${brief}</footer>`;
  }

  /* ---------- Messen: Bausteine unsichtbar in Druckgröße setzen ---------- */
  function messen(host, cfg, k, fuss) {
    let col = '';
    cfg.bereiche.forEach((b, bi) => {
      if (b.html) col += `<div data-s="${bi}" class="pl-m">${b.html}</div>`;
      b.gruppen.forEach((g, gi) => { col += `<div data-g="${bi}.${gi}" class="pl-m">${g.block(0, g.n, false)}</div>`; });
    });
    host.innerHTML = `<div class="al al-print pl-doc pl-mess pl-k${k}">
      <div data-m="mm" style="height:100mm"></div>
      <div data-m="kopf1" class="pl-m">${cfg.kopf(1, 1)}</div><div data-m="kopf2" class="pl-m">${cfg.kopf(2, 2)}</div>
      <div data-m="werb" class="pl-m">${cfg.werbung || ''}</div><div data-m="fuss" class="pl-m">${fuss}</div>
      <div class="pl-cols" style="--k:${k}"><div class="pl-col" data-m="col">${col}</div></div></div>`;
    const h = (el) => (el ? el.getBoundingClientRect().height : 0);
    const q = (s) => host.querySelector(s);
    const px = h(q('[data-m="mm"]')) / 100;   // px je mm
    const atoms = [];
    cfg.bereiche.forEach((b, bi) => {
      const lead = b.html ? h(q(`[data-s="${bi}"]`).firstElementChild) + ABSTAND.nachBereich * px : 0;   // Band ohne Außenabstand + Abstand zur Gruppe
      b.gruppen.forEach((g, gi) => {
        const box = q(`[data-g="${bi}.${gi}"]`), tab = box.querySelector('table'), tb = tab.tBodies[0];
        const rows = [...tb.rows].map((r) => r.getBoundingClientRect().height);
        const head = tb.getBoundingClientRect().top - box.getBoundingClientRect().top;
        const rest = Math.max(0, h(box) - head - rows.reduce((a, x) => a + x, 0));   // z. B. Linien der Tabelle
        atoms.push({ bi, gi, g, lead: gi === 0 ? lead : 0, head: head + rest, headF: head + rest, rows });
      });
    });
    const m = { px, k, atoms, kopf1: h(q('[data-m="kopf1"]')), kopf2: h(q('[data-m="kopf2"]')), werb: h(q('[data-m="werb"]')), fuss: fuss ? h(q('[data-m="fuss"]')) : 0 };
    // Gruppen, die länger als eine Spalte sein können, bekommen bei Teilung einen Kopf mit „Forts.“ – dessen Höhe eigens messen
    const grenze = SEITE.h * px - m.kopf1 - m.werb - m.fuss;
    const lang = atoms.filter((a) => a.head + a.rows.reduce((x, y) => x + y, 0) > grenze * 0.6);
    if (lang.length) {
      const colEl = q('[data-m="col"]');
      colEl.insertAdjacentHTML('beforeend', lang.map((a, i) => `<div data-f="${i}" class="pl-m">${a.g.block(0, 1, true)}</div>`).join(''));
      lang.forEach((a, i) => { const box = q(`[data-f="${i}"]`); a.headF = Math.max(a.head, h(box) - box.querySelector('table').tBodies[0].rows[0].getBoundingClientRect().height); });
    }
    return m;
  }

  /* ---------- Verteilen ----------
     atoms ab „start“ ({a: Gruppe, r: Zeile}) der Reihe nach in die Spalten „caps“ ([{soft, hard}] in px) füllen.
     soft = Zielhöhe (beim Ausgleichen kleiner), hard = volle Spaltenhöhe: eine Gruppe, die in eine leere Spalte passt (hard),
     wird nie geteilt. „bis“ ({a, r}, optional) begrenzt den Inhalt (Ausgleich einer einzelnen Seite).
     Rückgabe { cols: [[{a, von, bis, forts, lead}]], ende: null | {a, r} (Spalten reichten nicht) }. */
  function fuellen(m, start, caps, bis) {
    const A = m.atoms, G = { gruppe: ABSTAND.gruppe * m.px, bereich: ABSTAND.bereich * m.px };
    const cols = caps.map(() => []);
    let c = 0, y = 0, a = start.a, r = start.r;
    const sum = (rows, von, bis) => { let s = 0; for (let i = von; i < bis; i++) s += rows[i]; return s; };
    const E = bis || { a: A.length, r: 0 };
    while (a < E.a || (a === E.a && r < E.r)) {
      if (c >= caps.length) return { cols, ende: { a, r } };
      const at = A[a], n = a === E.a ? E.r : at.rows.length, forts = r > 0, cap = caps[c];
      const lead = forts ? 0 : at.lead, head = forts ? at.headF : at.head;
      const gap = y > 0 ? (lead ? G.bereich : G.gruppe) : 0;
      const total = lead + head + sum(at.rows, r, n);
      const setze = (bis) => { cols[c].push({ a, von: r, bis, forts, lead: lead > 0 }); y += gap + lead + head + sum(at.rows, r, bis); if (bis >= n) { a++; r = 0; } else { r = bis; c++; y = 0; } };
      if (y + gap + total <= cap.soft + EPS || (y === 0 && !forts && total <= cap.hard + EPS)) { setze(n); continue; }   // passt ganz (Rest einer geteilten Gruppe: nur bis zur Zielhöhe)
      const naechste = caps[c + 1] || cap;
      if (y > 0 && !forts && total <= naechste.hard + EPS) { c++; y = 0; continue; }   // nicht teilen: in die nächste Spalte
      // teilen (Gruppe ist länger als eine Spalte): so viele Zeilen, wie bis zur Zielhöhe passen
      const grenze = (y === 0 ? Math.max(cap.soft, Math.min(cap.hard, lead + head + sum(at.rows, r, Math.min(n, r + MIN_ZEILEN)))) : cap.soft) - y - gap - lead - head;
      let bis = r, frei = grenze + EPS;
      while (bis < n && at.rows[bis] <= frei) { frei -= at.rows[bis]; bis++; }
      if (n - bis === 1 && bis - r > MIN_ZEILEN) bis--;   // keine einzelne Zeile allein in der nächsten Spalte
      if (bis - r < Math.min(MIN_ZEILEN, n - r)) {
        if (y > 0) { c++; y = 0; continue; }              // zu wenig Platz am Spaltenende: Gruppe beginnt in der nächsten Spalte
        bis = Math.min(n, r + Math.max(1, bis - r));      // leere Spalte: wenigstens eine Zeile (sonst käme nichts voran)
      }
      setze(bis);
    }
    return { cols, ende: null };
  }

  /* Seiten ermitteln und die letzte(n) ausgleichen. modus: Fuß auf jeder Seite ('jede') oder nur der letzten ('letzte'). */
  function setzen(m, modus) {
    const H = SEITE.h * m.px, K = m.k;
    const hoehe = (p, mitFuss) => H - (p === 0 ? m.kopf1 + m.werb : m.kopf2) - (mitFuss ? m.fuss : 0);
    /* Spalten der Seiten von..bis-1 eines Satzes mit N Seiten; f < 1 senkt die Zielhöhe (Ausgleich) */
    const caps = (N, von, bis, f = 1) => {
      const out = [];
      for (let p = von; p < bis; p++) {
        const hard = Math.max(40, hoehe(p, m.fuss > 0 && (modus === 'jede' || p === N - 1)));
        const soft = Math.min(hard, Math.max(ABSTAND.spalteMin * m.px, hard * f));
        for (let i = 0; i < K; i++) out.push({ soft, hard });
      }
      return out;
    };
    let N = 1, res;
    for (; N <= 80; N++) { res = fuellen(m, { a: 0, r: 0 }, caps(N, 0, N)); if (!res.ende) break; }
    const seiten = [];
    for (let p = 0; p < N; p++) seiten.push(res.cols.slice(p * K, (p + 1) * K));
    const anfang = (p) => { const fr = seiten[p] && seiten[p].flat()[0]; return fr ? { a: fr.a, r: fr.von } : null; };
    /* Spalten der Seiten von..bis-1 ausgleichen: kleinste Zielhöhe, mit der ihr Inhalt in ihre Spalten passt */
    const ausgleichen = (von, bis) => {
      const start = anfang(von), stop = bis < N ? anfang(bis) : null;
      if (!start || (bis < N && !stop)) return;
      let lo = 0, hi = 1, best = null;
      for (let i = 0; i < 16; i++) {
        const f = (lo + hi) / 2, t = fuellen(m, start, caps(N, von, bis, f), stop || undefined);
        if (t.ende) lo = f; else { hi = f; best = t; }
      }
      if (best) for (let p = von; p < bis; p++) seiten[p] = best.cols.slice((p - von) * K, (p - von + 1) * K);
    };
    // letzte Seite ausgleichen; ist sie zu weniger als einem Drittel gefüllt, die letzten beiden gemeinsam
    const hFrag = (fr) => { const at = m.atoms[fr.a]; let s = (fr.lead ? at.lead : 0) + (fr.forts ? at.headF : at.head); for (let i = fr.von; i < fr.bis; i++) s += at.rows[i]; return s; };
    const belegt = seiten[N - 1].reduce((s, col) => s + col.reduce((x, fr) => x + hFrag(fr), 0), 0);
    const platz = caps(N, N - 1, N).reduce((s, c) => s + c.hard, 0);
    const ab = N >= 2 && belegt < platz / 3 ? N - 2 : N - 1;
    ausgleichen(ab, N);
    for (let p = 0; p < ab; p++) ausgleichen(p, p + 1);   // volle Seiten: gleicher Inhalt, Spalten möglichst gleich hoch
    return seiten;
  }

  /* cfg: { host (#print-root), bereiche: [{ html, gruppen: [{ n, block(von, bis, forts) }] }], kopf(seite, seiten), werbung?,
            fuss?: {spalten, zeilen}, hinweis?: [Zeilen], modus: 'jede' | 'letzte', spalten?: 3 | 4 }
     Rückgabe { html, seiten, spalten } – html ersetzt den Inhalt von host. */
  function liste(cfg) {
    const host = cfg.host, modus = cfg.modus === 'letzte' ? 'letzte' : 'jede';
    const fuss = fussHTML(cfg.fuss, cfg.hinweis, 'quer');
    const alt = host.innerHTML;
    host.classList.add('pl-messen');
    let wahl = null;
    try {
      for (const k of (cfg.spalten ? [cfg.spalten] : [3, 4])) {
        const m = messen(host, cfg, k, fuss), seiten = setzen(m, modus);
        if (!wahl || seiten.length < wahl.seiten.length) wahl = { m, seiten };
      }
    } finally {
      host.classList.remove('pl-messen');
      host.innerHTML = alt;
    }
    const { m, seiten } = wahl, N = seiten.length, A = m.atoms;
    const html = seiten.map((cols, p) => `<section class="pl-page">${cfg.kopf(p + 1, N)}${p === 0 ? cfg.werbung || '' : ''}
      <div class="pl-cols" style="--k:${m.k}">${cols.map((col) => `<div class="pl-col">${col.map((fr) => {
        const at = A[fr.a];
        return (fr.lead ? cfg.bereiche[at.bi].html : '') + at.g.block(fr.von, fr.bis, fr.forts);
      }).join('')}</div>`).join('')}</div>${fuss && (modus === 'jede' || p === N - 1) ? fuss : ''}</section>`).join('');
    return { html: `<div class="al al-print pl-doc pl-k${m.k}" data-seiten="${N}" data-spalten="${m.k}" data-fuss="${fuss ? modus : 'ohne'}">${html}</div>`, seiten: N, spalten: m.k };
  }

  root.AngebotDruck = { liste, fussHTML, SEITE };
})(window);
