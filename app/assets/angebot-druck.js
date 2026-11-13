/* Angebot · Satz der Druckfassung „Angebotsansicht“ (A4 quer) für die Angebotsseite (frontend.js, Wunsch des Inhabers 13.11.2026).
   Der Druck sieht aus wie die Vorschau (Angebotsansicht am Bildschirm): Kopf mit Logo und Titel, Bereiche als abgerundete
   Balken über den Spalten ihres Bereichs, Gruppen als Blöcke mit „€/kg“, abgerundete gestreifte Zeilen – immer drei Spalten.
   Regeln des Satzes:
   - Ein Block (Gruppe mit Kopf und allen Zeilen) steht immer vollständig in einer Spalte auf einer Seite.
   - Ein Bereich bleibt zusammen (seine Gruppen nebeneinander wie in der Vorschau, kleine Bereiche nebeneinander in einer
     Zeile), wenn er auf den Rest der Seite passt. Passt er nicht, beginnt er auf der nächsten Seite – außer es bliebe dadurch
     viel Platz leer (mehr als LOCH der Seite) oder er ist höher als eine ganze Seite: dann wird zwischen den Gruppen
     umbrochen und der Balken auf der neuen Seite wiederholt („Forts.“).
   - Einziger Sonderfall: eine einzelne Gruppe, die höher ist als eine ganze Seitenspalte, läuft in der nächsten Spalte
     derselben Seite weiter (Gruppenkopf mit „Forts.“), erst danach auf der nächsten Seite. Die sortierte Gesamtliste ohne
     Gruppen („verteilen“) wird wie am Bildschirm gleichmäßig auf die drei Spalten verteilt.
   - Kein Seitenwechsel je Bereich: die Bereiche laufen in der Reihenfolge des Angebots fortlaufend durch die Seiten.
   Damit das stimmt, wird nicht geschätzt, sondern gemessen: die Bausteine werden einmal unsichtbar in der Größe des Drucks
   gesetzt, dann rechnerisch auf Seiten fester Höhe verteilt. Gesetzt wird in den Maßen der Bildschirmansicht (px) auf
   einer Fläche von BREITE px Breite und für A4 quer verkleinert (Faktor --z, angebot-druck.css) – unabhängig von Bildschirm und Zoom.
   Jede Seite hat einen Kopf (Seite 1 mit Logo, danach schlank mit „Seite x von y“). Der Hinweis (Mengen, Fracht) und die
   Fußzeile des Briefbogens stehen am Fuß der letzten Seite („letzte“, Vorgabe) oder jeder Seite („jede“); der Platz dafür
   ist freigehalten (nichts wird überdeckt).
   Kein Zugriff auf Daten: frontend.js liefert fertige HTML-Bausteine (nur aufgelöste Angebotsdaten, GR-001/GR-002).
   Schnittstelle: window.AngebotDruck = { liste(cfg), fussHTML(fuss, hinweis, art), SEITE }. */
(function (root) {
  'use strict';
  const SEITE = { b: 279, h: 193 };          // Satzspiegel in mm (A4 quer 297 × 210, Ränder 9 mm seitlich, 8 mm oben/unten, 1 mm Reserve)
  const BREITE = 1240;                        // Satzbreite in px der Bildschirmansicht – 13,5 px Schrift werden im Druck rund 8,6 pt
  const SPALTEN = 3;                          // immer drei Spalten (Wunsch des Inhabers)
  const ABSTAND = { gruppe: 14, balken: 10, band: 16 };   // px wie in angebot-druck.css: zwischen Blöcken, unter dem Balken, zwischen Zeilen von Bereichen
  const MIN_ZEILEN = 3;                       // so viele Zeilen einer geteilten Gruppe stehen mindestens in einer Spalte
  const LOCH = 0.33;                          // bliebe mehr als dieser Anteil der Seite leer, wird der Bereich zwischen den Gruppen umbrochen
  const NEBEN = 0.15;                         // Bereiche nebeneinander nur, wenn es deutlich Platz spart (wie am Bildschirm)
  const EPS = 0.5;                            // px Toleranz beim Vergleichen gemessener Höhen
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
  const zeilen = (t) => String(t ?? '').split('\n').map((l) => l.trim()).filter(Boolean);

  /* Fußzeile des Briefbogens: Siegel, drei Textspalten, zwei Zeilen (Handelsregister); darüber der Hinweis (Mengen, Fracht).
     art „quer“: alles in einer Reihe über die Seitenbreite (Zeilen als vierter Block); „hoch“: Zeilen unter den Spalten. */
  function fussHTML(fuss, hinweis, art) {
    const f = fuss || {}, sp = Array.isArray(f.spalten) ? f.spalten : [], ze = (Array.isArray(f.zeilen) ? f.zeilen : []).filter((z) => String(z || '').trim());
    const hin = (hinweis || []).filter((l) => String(l || '').trim());
    const spalten = sp.map((t) => zeilen(t)).filter((l) => l.length);
    if (!spalten.length && !ze.length && !hin.length) return '';
    const brief = spalten.length || ze.length ? `<div class="pl-brief"><img class="pl-siegel" src="assets/druck-siegel.jpg" width="316" height="250" alt="">
        ${spalten.map((l) => `<p class="pl-bs">${l.map(esc).join('<br>')}</p>`).join('')}
        ${ze.length ? `<p class="pl-bz">${ze.map((z) => `<span>${esc(z)}</span>`).join(' ')}</p>` : ''}</div>` : '';
    return `<footer class="pl-fuss pl-fuss-${art === 'hoch' ? 'hoch' : 'quer'}">${hin.length ? `<p class="pl-hinweis">${hin.map((l, i) => `<span${i === 0 ? ' class="lead"' : ''}>${esc(l)}</span>`).join(' ')}</p>`.replace(/([^.!?:;…])<\/span> <span/g, '$1</span> · <span') : ''}${brief}</footer>`;
  }

  /* ---------- Messen: Bausteine unsichtbar in Druckgröße setzen ---------- */
  function messen(host, cfg, fuss) {
    const cs = [1, 2, 3];
    let col = '', balken = '';
    cfg.bereiche.forEach((b, bi) => {
      if (b.name) balken += cs.map((c) => `<div class="pl-m pl-mb" data-b="${bi}.${c}" style="--c:${c}">${b.balken(false)}</div><div class="pl-m pl-mb" data-bf="${bi}.${c}" style="--c:${c}">${b.balken(true)}</div>`).join('');
      b.gruppen.forEach((g, gi) => { col += `<div data-g="${bi}.${gi}" class="pl-m">${g.block(0, g.n, false)}</div>`; });
    });
    host.innerHTML = `<div class="al al-print pl-doc pl-mess" style="--z:${zFaktor()}"><div class="pl-in">
      <div data-m="mm" style="height:100mm"></div>
      <div data-m="kopf1" class="pl-m">${cfg.kopf(1, 1)}</div><div data-m="kopf2" class="pl-m">${cfg.kopf(2, 2)}</div>
      <div data-m="werb" class="pl-m">${cfg.werbung || ''}</div><div data-m="fuss" class="pl-m">${fuss}</div>
      ${balken}<div class="pl-mcol" data-m="col">${col}</div></div></div>`;
    const h = (el) => (el ? el.getBoundingClientRect().height : 0);
    const q = (s) => host.querySelector(s);
    const px = h(q('[data-m="mm"]')) / 100;   // px je mm
    const secs = cfg.bereiche.map((b, bi) => {
      const bar = [0, 0, 0, 0], barF = [0, 0, 0, 0];
      if (b.name) cs.forEach((c) => { bar[c] = h(q(`[data-b="${bi}.${c}"]`).firstElementChild); barF[c] = h(q(`[data-bf="${bi}.${c}"]`).firstElementChild); });
      const units = b.gruppen.map((g, gi) => {
        const box = q(`[data-g="${bi}.${gi}"]`), tb = box.querySelector('table').tBodies[0];
        const rows = [...tb.rows].map((r) => r.getBoundingClientRect().height);
        const head = h(box) - rows.reduce((a, x) => a + x, 0);   // Gruppenkopf samt Linien
        return { bi, gi, g, h: h(box), head, headF: head, rows, verteilen: !!g.verteilen };
      });
      return { bi, name: !!b.name, bar, barF, units };
    });
    const m = { px, H: SEITE.h * px / zFaktor(), secs, kopf1: h(q('[data-m="kopf1"]')), kopf2: h(q('[data-m="kopf2"]')), werb: h(q('[data-m="werb"]')), fuss: fuss ? h(q('[data-m="fuss"]')) : 0 };
    // Gruppen, die geteilt werden können (höher als eine Seitenspalte, „verteilen“), bekommen einen Kopf mit „Forts.“ – eigens messen
    const lang = [];
    secs.forEach((s) => s.units.forEach((u) => { if (u.verteilen || u.h > (m.H - m.kopf2) * 0.6) lang.push(u); }));
    if (lang.length) {
      q('[data-m="col"]').insertAdjacentHTML('beforeend', lang.map((u, i) => `<div data-f="${i}" class="pl-m">${u.g.block(0, 1, true)}</div>`).join(''));
      lang.forEach((u, i) => { const box = q(`[data-f="${i}"]`); u.headF = Math.max(u.head, h(box) - box.querySelector('table').tBodies[0].rows[0].getBoundingClientRect().height); });
    }
    return m;
  }
  /* Verkleinerung der Satzfläche auf den Satzspiegel (px der Bildschirmansicht → A4 quer); 1 mm = 96/25,4 px */
  function zFaktor() { return Math.round(SEITE.b * 96 / 25.4 / BREITE * 100000) / 100000; }

  /* ---------- Verteilen ----------
     Seite für Seite: gesucht ist die Folge von Zeilen („Bändern“), die am meisten auf die Seite bringt. Ein Band ist ein
     Bereich in 1–3 Spalten oder mehrere Bereiche nebeneinander (zusammen drei Spalten) – wie am Bildschirm, mit demselben
     Aufschlag NEBEN. Am Seitenende darf der nächste Bereich zwischen seinen Gruppen umbrochen werden (er bekommt die noch
     freien Spalten der Zeile), wenn sonst mehr als LOCH der Seite leer bliebe oder er auf keine ganze Seite passt. */
  function setzen(m, modus) {
    const S = m.secs, n = S.length, G = ABSTAND.gruppe, BAND = ABSTAND.band, jede = modus === 'jede';
    const balken = (s, c, forts) => (s.name ? (forts ? s.barF[c] : s.bar[c]) + ABSTAND.balken : 0);
    const sum = (rows, von, bis) => { let x = 0; for (let i = von; i < bis; i++) x += rows[i]; return x; };
    const ganz = (u) => ({ gi: u.gi, von: 0, bis: u.rows.length, forts: false, h: u.h });
    /* Blöcke in fester Reihenfolge ungeteilt auf c Spalten: höchste Spalte so niedrig wie möglich (wie am Bildschirm) */
    const teilen = (us, c) => {
      const k = us.length;
      if (!k) return { h: 0, cols: [] };
      c = Math.max(1, Math.min(c, k));
      const pre = [0];
      for (const u of us) pre.push(pre[pre.length - 1] + u.h);
      const hoehe = (a, i) => pre[i] - pre[a] + G * (i - a - 1);
      const f = [[0].concat(Array(k).fill(Infinity))], cut = [[]];
      for (let j = 1; j <= c; j++) {
        f[j] = [Infinity]; cut[j] = [0];
        for (let i = 1; i <= k; i++) {
          let best = Infinity, at = j - 1;
          for (let a = j - 1; a < i; a++) { const v = Math.max(f[j - 1][a], hoehe(a, i)); if (v < best - 1e-9) { best = v; at = a; } }
          f[j][i] = best; cut[j][i] = at;
        }
      }
      const cols = [];
      for (let j = c, i = k; j >= 1; j--) { const a = cut[j][i]; cols.unshift(us.slice(a, i).map(ganz)); i = a; }
      return { h: f[c][k], cols, inhalt: pre[k] };
    };
    const memo = new Map();
    const lage = (si, u0, c) => { const key = si + '.' + u0 + '.' + c; if (!memo.has(key)) memo.set(key, teilen(S[si].units.slice(u0), c)); return memo.get(key); };
    /* Mögliche Zeilen ab Bereich i (ab seiner Gruppe u0): der Bereich allein in 1–3 Spalten oder mit den folgenden
       Bereichen nebeneinander (zusammen höchstens drei Spalten); frei = Spalten, die rechts noch übrig sind */
    const kmemo = new Map();
    const kandidaten = (i, u0) => {
      const key = i + '.' + u0;
      if (kmemo.has(key)) return kmemo.get(key);
      const out = [];
      const rec = (j, frei, teile, inhalt) => {
        const s = S[j], v = j === i ? u0 : 0, forts = v > 0, anz = s.units.length - v;
        if (s.units.slice(v).some((u) => u.verteilen)) return;   // Gesamtliste: wird verteilt (fuellen)
        for (let c = 1; c <= Math.min(frei, anz); c++) {
          const l = lage(j, v, c);
          const t = teile.concat({ si: j, c, forts, cols: l.cols, h: balken(s, c, forts) + l.h });
          const h = Math.max(...t.map((x) => x.h));
          out.push({ teile: t, h, bis: j + 1, frei: frei - c, inhalt: inhalt + l.inhalt, kost: h * (1 + NEBEN * (t.length - 1)) });
          if (j + 1 < n && frei - c >= 1) rec(j + 1, frei - c, t, inhalt + l.inhalt);
        }
      };
      rec(i, SPALTEN, [], 0);
      kmemo.set(key, out);
      return out;
    };
    const kap = (p, res) => m.H - (p === 0 ? m.kopf1 + m.werb : m.kopf2) - (res ? m.fuss : 0);

    /* Zwischen Gruppen umbrechen: so viele Gruppen des Bereichs i (ab Gruppe u0, Zeile r0), wie in „spalten“ Spalten der
       Höhe R passen. Rückgabe { teil, a, r, inhalt } (a, r: nächste Gruppe/Zeile) oder null (nichts passt). */
    const fuellen = (i, u0, r0, R, voll, spalten) => {
      const s = S[i], forts = u0 > 0 || r0 > 0, bar = balken(s, spalten, forts), room = R - bar;
      const cols = [], colH = [];
      for (let k = 0; k < spalten; k++) { cols.push([]); colH.push(0); }
      let c = 0, a = u0, r = r0, nurGanze = true, inhalt = 0;
      const stuecke = (u, von0, cap, anz, minZ) => {   // Zeilen einer Gruppe auf höchstens „anz“ Spalten der Höhe cap
        const out = []; let von = von0;
        for (let k = 0; k < anz && von < u.rows.length; k++) {
          const head = von > 0 ? u.headF : u.head;
          let bis = von, frei = cap - head + EPS;
          while (bis < u.rows.length && u.rows[bis] <= frei) { frei -= u.rows[bis]; bis++; }
          if (u.rows.length - bis === 1 && bis - von > minZ) bis--;   // keine einzelne Zeile allein in der nächsten Spalte
          if (bis - von < Math.min(minZ, u.rows.length - von)) break;
          out.push({ von, bis, h: head + sum(u.rows, von, bis) });
          von = bis;
        }
        return { out, ende: von };
      };
      while (a < s.units.length) {
        const u = s.units[a];
        if (r > 0 || u.verteilen || u.h > voll - balken(s, SPALTEN, true) + EPS) {   // Sonderfall: Gruppe höher als eine Seitenspalte
          if (colH[c] > 0) { if (c < spalten - 1) c++; else break; }
          const frei = spalten - c, minZ = u.verteilen ? 1 : MIN_ZEILEN;
          let st = stuecke(u, r, room, frei, minZ);
          if (!st.out.length) break;
          if (st.ende >= u.rows.length) {   // endet auf dieser Seite: ihre Spalten gleich hoch
            const ziel = u.verteilen ? frei : st.out.length;
            let lo = 0, hi = room;
            for (let k = 0; k < 14; k++) { const mid = (lo + hi) / 2, t = stuecke(u, r, mid, ziel, minZ); if (t.out.length && t.ende >= u.rows.length) { hi = mid; st = t; } else lo = mid; }
          }
          st.out.forEach((x, k) => { cols[c + k].push({ gi: u.gi, von: x.von, bis: x.bis, forts: x.von > 0, h: x.h }); colH[c + k] = x.h; inhalt += x.h; });
          c += st.out.length - 1; nurGanze = false;
          if (st.ende >= u.rows.length) { a++; r = 0; continue; }
          r = st.ende; break;
        }
        const gap = colH[c] > 0 ? G : 0;
        if (colH[c] + gap + u.h <= room + EPS) { cols[c].push(ganz(u)); colH[c] += gap + u.h; }
        else if (c < spalten - 1 && u.h <= room + EPS) { c++; cols[c].push(ganz(u)); colH[c] = u.h; }
        else break;
        inhalt += u.h; a++;
      }
      if (a === u0 && r === r0) return null;
      let hmax = Math.max(...colH), sp = cols;
      if (nurGanze) { const l = teilen(s.units.slice(u0, a), spalten); hmax = l.h; sp = l.cols; while (sp.length < spalten) sp.push([]); }   // Spalten ausgleichen
      return { teil: { si: i, c: spalten, forts, cols: sp, h: bar + hmax }, a, r, inhalt };
    };

    /* Eine Seite füllen ab Zustand st ({i, u0, r0}); res: Platz für die Fußzeile freihalten. Rückgabe { bands, i, u0, r0, y } */
    const seite = (st, p, res, resNext) => {
      const K = kap(p, res), voll = kap(p + 1, resNext);
      // best[i]: günstigste Folge ganzer Zeilen bis vor Bereich i (Kosten wie am Bildschirm, y = tatsächliche Höhe)
      const best = {};
      best[st.i] = { y: 0, kost: 0, inhalt: 0, bands: [] };
      let A = null, B = null;
      for (let i = st.i; i <= n; i++) {
        const z = best[i];
        if (!z) continue;
        const u0 = i === st.i ? st.u0 : 0, r0 = i === st.i ? st.r0 : 0;
        if (u0 === 0 && r0 === 0 || i === st.i) A = { i, u0, r0, y: z.y, inhalt: z.inhalt, bands: z.bands };   // weitester Stand ohne Umbruch im Bereich
        if (i >= n) break;
        const lueck = z.y > 0 ? BAND : 0, R = K - z.y - lueck;
        const ks = r0 > 0 ? [] : kandidaten(i, u0).filter((k) => k.h <= R + EPS);
        for (const k of ks) {
          const w = { y: z.y + lueck + k.h, kost: z.kost + lueck + k.kost, inhalt: z.inhalt + k.inhalt, bands: z.bands.concat(k) };
          if (!best[k.bis] || w.kost < best[k.bis].kost - EPS) best[k.bis] = w;
        }
        // Umbruch zwischen Gruppen: ganze Bereiche links davon (oder keiner), der nächste Bereich teilweise in den freien Spalten
        for (const pre of [{ teile: [], h: 0, bis: i, frei: SPALTEN, inhalt: 0 }].concat(ks.filter((k) => k.frei >= 1 && k.bis < n))) {
          const j = pre.bis, t = fuellen(j, j === i ? u0 : 0, j === i ? r0 : 0, R, voll, pre.frei);
          if (!t) continue;
          const band = { teile: pre.teile.concat(t.teil), h: Math.max(pre.h, t.teil.h) };
          const w = { y: z.y + lueck + band.h, kost: z.kost + lueck + band.h, inhalt: z.inhalt + pre.inhalt + t.inhalt, bands: z.bands.concat(band) };
          if (t.a >= S[j].units.length) { if (!best[j + 1] || w.kost < best[j + 1].kost - EPS) best[j + 1] = w; continue; }   // Bereich doch fertig (Sonderfall)
          if (!B || w.inhalt > B.inhalt + EPS) B = { i: j, u0: t.a, r0: t.r, y: w.y, inhalt: w.inhalt, bands: w.bands };
        }
      }
      if (A.i >= n) return A;
      const passtGanz = A.r0 === 0 && kandidaten(A.i, A.u0).some((k) => k.h <= voll + EPS);   // der nächste Bereich passt als Ganzes auf eine neue Seite
      const leer = 1 - A.inhalt / (SPALTEN * K);
      if (passtGanz && leer <= LOCH) return A;
      return B && B.inhalt > A.inhalt + EPS ? B : A;
    };

    /* Ab Zustand st ({p, i, u0, r0}) alle Seiten füllen; res(p): auf Seite p Platz für die Fußzeile freihalten */
    const lauf = (st, res) => {
      const seiten = {}, starts = {};
      let p = st.p, z = { i: st.i, u0: st.u0, r0: st.r0 }, y = 0, runde = 0;
      for (;;) {
        starts[p] = { p, i: z.i, u0: z.u0, r0: z.r0 };
        const e = seite(z, p, res(p), res(p + 1));
        seiten[p] = e.bands; y = e.y;
        if (!e.bands.length && e.i < n && p > 0) {
          // leere Folgeseite und trotzdem kein Platz (z. B. sehr hoher Kopf): die Gruppe trotzdem setzen, damit es weitergeht
          const s = S[e.i], u = s.units[e.u0], bar = balken(s, SPALTEN, e.u0 > 0);
          seiten[p] = [{ teile: [{ si: e.i, c: SPALTEN, forts: e.u0 > 0, cols: [[ganz(u)]], h: bar + u.h }], h: bar + u.h }];
          y = bar + u.h;
          z = e.u0 + 1 >= s.units.length ? { i: e.i + 1, u0: 0, r0: 0 } : { i: e.i, u0: e.u0 + 1, r0: 0 };
        } else z = { i: e.i, u0: e.u0, r0: e.r0 };
        if (z.i >= n || runde++ > 400) break;
        p++;
      }
      return { seiten, starts, p, y };
    };

    const L = lauf({ p: 0, i: 0, u0: 0, r0: 0 }, () => jede);
    if (!jede && m.fuss > 0 && L.y + m.fuss > kap(L.p, false) + EPS) {
      // Fußzeile passt nicht mehr unter die letzte Seite: diese Seite mit freigehaltenem Fuß neu setzen
      const letzte = L.p, L2 = lauf(L.starts[letzte], (p) => p >= letzte);
      for (const p of Object.keys(L2.seiten)) L.seiten[p] = L2.seiten[p];
      L.p = L2.p;
    }
    const seiten = [];
    for (let p = 0; p <= L.p; p++) seiten.push(L.seiten[p] || []);
    return seiten;
  }

  /* cfg: { host (#print-root), bereiche: [{ name, balken(forts), gruppen: [{ n, block(von, bis, forts), verteilen? }] }],
            kopf(seite, seiten), werbung?, fuss?: {spalten, zeilen}, hinweis?: [Zeilen], modus: 'letzte' | 'jede' }
     Rückgabe { html, seiten, spalten, geteilt } – html ersetzt den Inhalt von host. */
  function liste(cfg) {
    const host = cfg.host, modus = cfg.modus === 'jede' ? 'jede' : 'letzte';
    const fuss = fussHTML(cfg.fuss, cfg.hinweis, 'quer');
    const alt = host.innerHTML;
    host.classList.add('pl-messen');
    let m;
    try { m = messen(host, cfg, fuss); } finally { host.classList.remove('pl-messen'); host.innerHTML = alt; }
    const seiten = setzen(m, modus), N = seiten.length;
    let geteilt = 0, bereichForts = 0;
    const band = (b) => `<div class="al-band">${b.teile.map((t) => {
      const ber = cfg.bereiche[t.si];
      if (t.forts) bereichForts++;
      return `<section class="al-sec" style="--c:${t.c}">${ber.name ? ber.balken(t.forts) : ''}
        <div class="al-cols" style="--k:${t.c}">${t.cols.map((col) => `<div class="al-col">${col.map((fr) => { if (fr.forts) geteilt++; return ber.gruppen[fr.gi].block(fr.von, fr.bis, fr.forts); }).join('')}</div>`).join('')}</div></section>`;
    }).join('')}</div>`;
    const html = seiten.map((bs, p) => `<section class="pl-page"><div class="pl-in">${cfg.kopf(p + 1, N)}${p === 0 ? cfg.werbung || '' : ''}
      ${bs.map(band).join('')}${fuss && (modus === 'jede' || p === N - 1) ? fuss : ''}</div></section>`).join('');
    return { html: `<div class="al al-print pl-doc" style="--z:${zFaktor()}" data-seiten="${N}" data-spalten="${SPALTEN}" data-fuss="${fuss ? modus : 'ohne'}" data-geteilt="${geteilt}" data-bereich-forts="${bereichForts}">${html}</div>`,
      seiten: N, spalten: SPALTEN, geteilt };
  }

  root.AngebotDruck = { liste, fussHTML, SEITE };
})(window);
