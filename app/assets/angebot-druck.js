/* Angebot · Satz der Druckfassung „Angebotsansicht“ (A4 quer) für die Angebotsseite (frontend.js, Wunsch des Inhabers 13.11.2026).
   Der Druck sieht aus wie die Vorschau (Angebotsansicht am Bildschirm): Kopf mit Logo und Titel, Bereiche als abgerundete
   Balken über den Spalten ihres Bereichs, Gruppen als Blöcke mit „€/kg“, abgerundete gestreifte Zeilen – immer drei Spalten.
   Wochenangebot, Kundenangebote und Einzelangebote nutzen denselben Satz. Regeln:
   - Ein Block (Gruppe mit Kopf und allen Zeilen) steht immer vollständig in einer Spalte auf einer Seite.
   - Die Seiten werden fortlaufend gefüllt: jede Seite nimmt so viele Blöcke auf wie möglich. Die Blöcke eines Bereichs
     stehen in der Reihenfolge des Angebots nebeneinander in möglichst gleich hohen Spalten (links oben der erste Block);
     kleine Bereiche stehen nebeneinander in einer Zeile, wenn das Höhe spart.
   - Ein Bereich beginnt auf der laufenden Seite, sobald sein Balken und mindestens ein ganzer Block Platz haben. Umbrochen
     wird nur zwischen Blöcken; auf der nächsten Seite steht der Balken noch einmal („Forts.“).
   - Einzige Ausnahme vom ungeteilten Block: eine Gruppe, die allein höher ist als eine ganze Seitenspalte, wird in gleich
     hohe Teile zerlegt (Gruppenkopf mit „Forts.“), die wie Blöcke gesetzt werden. Die sortierte Gesamtliste ohne Gruppen
     („verteilen“) wird gleichmäßig auf die drei Spalten jeder Seite verteilt.
   - Dichte: gesetzt wird in drei festen Stufen (STUFEN: normal, kompakt, eng – Schrift 8,3 / 7,9 / 7,5 pt, dazu knappere
     Zeilen und Abstände in angebot-druck.css). Gewählt wird automatisch die größte Schrift, mit der das Angebot nicht mehr
     Seiten braucht als mit der kleinsten (cfg.stufe legt eine Stufe fest, zum Vergleich).
   Damit das stimmt, wird nicht geschätzt, sondern gemessen: die Bausteine werden je Stufe einmal unsichtbar in der Größe
   des Drucks gesetzt, dann rechnerisch auf Seiten fester Höhe verteilt. Gesetzt wird in den Maßen der Bildschirmansicht
   (px) auf einer Fläche von „breite“ px und für A4 quer verkleinert (Faktor --z) – unabhängig von Bildschirm und Zoom.
   Jede Seite hat einen Kopf (Seite 1 mit Logo, danach schlank mit „Seite x von y“). Der Hinweis (Mengen, Fracht) und die
   Fußzeile des Briefbogens stehen am Fuß der letzten Seite („letzte“, Vorgabe) oder jeder Seite („jede“); der Platz dafür
   ist freigehalten (nichts wird überdeckt).
   Kein Zugriff auf Daten: frontend.js liefert fertige HTML-Bausteine (nur aufgelöste Angebotsdaten, GR-001/GR-002).
   Schnittstelle: window.AngebotDruck = { liste(cfg), fussHTML(fuss, hinweis, art), SEITE, STUFEN }. */
(function (root) {
  'use strict';
  const SEITE = { b: 279, h: 193 };          // Satzspiegel in mm (A4 quer 297 × 210, Ränder 9 mm seitlich, 8 mm oben/unten, 1 mm Reserve)
  const SPALTEN = 3;                          // immer drei Spalten (Wunsch des Inhabers)
  /* Stufen der Dichte, von groß nach klein: Satzbreite in px der Bildschirmansicht (13 px Schrift werden im Druck
     8,3 / 7,9 / 7,5 pt); Zeilenhöhe und Abstände je Stufe stehen in angebot-druck.css (.pl-normal, .pl-kompakt, .pl-eng) */
  const STUFEN = [{ name: 'normal', breite: 1240 }, { name: 'kompakt', breite: 1310 }, { name: 'eng', breite: 1370 }];
  const MIN_ZEILEN = 3;                       // ein einzelner Block wird erst ab so vielen Zeilen je Spalte über die Spalten verteilt
  const EPS = 0.5;                            // px Toleranz beim Vergleichen gemessener Höhen
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
  const LEER = '<div class="al-st al-st-leer" aria-hidden="true"><h3>&nbsp;</h3></div>';   // unsichtbarer Balken: Bereich ohne Namen neben einem benannten (Blöcke der Zeile beginnen bündig, wie am Bildschirm)
  const zeilen = (t) => String(t ?? '').split('\n').map((l) => l.trim()).filter(Boolean);
  const summe = (a) => a.reduce((x, y) => x + y, 0);
  /* Verkleinerung der Satzfläche auf den Satzspiegel (px der Bildschirmansicht → A4 quer); 1 mm = 96/25,4 px */
  const zFaktor = (st) => Math.round(SEITE.b * 96 / 25.4 / st.breite * 100000) / 100000;

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

  /* ---------- Messen: Bausteine unsichtbar in Druckgröße setzen (eine Stufe) ----------
     Höhen in px der Satzfläche, Abstände eingeschlossen (Balken mit seinem Abstand nach unten, Kopf mit seinem Abstand).
     Die Abstände zwischen Blöcken und Zeilen von Bereichen stehen nur in angebot-druck.css (--ab-gruppe, --ab-band). */
  function messen(host, cfg, fuss, st) {
    const cs = [1, 2, 3];
    let col = '', balken = '';
    cfg.bereiche.forEach((b, bi) => {
      if (b.name) balken += cs.map((c) => `<div class="pl-m pl-mb" data-b="${bi}.${c}" style="--c:${c}">${b.balken(false)}</div><div class="pl-m pl-mb" data-bf="${bi}.${c}" style="--c:${c}">${b.balken(true)}</div>`).join('');
      b.gruppen.forEach((g, gi) => { col += `<div data-g="${bi}.${gi}" class="pl-m">${g.block(0, g.n, false)}</div><div data-f="${bi}.${gi}" class="pl-m">${g.block(0, 1, true)}</div>`; });
    });
    host.innerHTML = `<div class="al al-print pl-doc pl-mess pl-${st.name}" style="--z:${zFaktor(st)}"><div class="pl-in">
      <div data-m="mm" style="height:100mm"></div>
      <div data-m="kopf1" class="pl-m">${cfg.kopf(1, 1)}</div><div data-m="kopf2" class="pl-m">${cfg.kopf(2, 2)}</div>
      <div data-m="werb" class="pl-m">${cfg.werbung || ''}</div><div data-m="fuss" class="pl-m">${fuss}</div><div data-m="leer" class="pl-m pl-mb" style="--c:1">${LEER}</div>
      ${balken}<div class="pl-mcol" data-m="col">${col}</div></div></div>`;
    const h = (el) => (el ? el.getBoundingClientRect().height : 0);
    const q = (s) => host.querySelector(s);
    const stil = getComputedStyle(q('.pl-doc')), ab = (n) => parseFloat(stil.getPropertyValue('--ab-' + n)) || 0;
    const secs = cfg.bereiche.map((b, bi) => {
      const bar = [0, 0, 0, 0], barF = [0, 0, 0, 0];
      if (b.name) cs.forEach((c) => { bar[c] = h(q(`[data-b="${bi}.${c}"]`)); barF[c] = h(q(`[data-bf="${bi}.${c}"]`)); });
      const units = b.gruppen.map((g, gi) => {
        const box = q(`[data-g="${bi}.${gi}"]`), boxF = q(`[data-f="${bi}.${gi}"]`);
        const rows = [...box.querySelector('table').tBodies[0].rows].map((r) => r.getBoundingClientRect().height);
        const head = h(box) - summe(rows);   // Gruppenkopf samt Linien
        return { gi, h: h(box), head, headF: Math.max(head, h(boxF) - h(boxF.querySelector('table').tBodies[0].rows[0])), rows, verteilen: !!g.verteilen };   // headF: Kopf mit „Forts.“
      });
      return { name: !!b.name, bar, barF, units };
    });
    return { H: SEITE.h * h(q('[data-m="mm"]')) / 100 / zFaktor(st), secs, kopf1: h(q('[data-m="kopf1"]')), kopf2: h(q('[data-m="kopf2"]')), werb: h(q('[data-m="werb"]')),
      fuss: fuss ? h(q('[data-m="fuss"]')) : 0, leer: h(q('[data-m="leer"]')), G: ab('gruppe'), BAND: ab('band') };
  }

  /* ---------- Verteilen ----------
     Rückgabe: Seiten [{ bands, y, K }] – bands: Zeilen der Seite, jede mit „teile“ (ein Bereich in 1–3 Spalten oder mehrere
     Bereiche nebeneinander, zusammen drei Spalten): { si: Bereich, c: Spalten, forts, leer, cols: [[{ gi, von, bis, forts, h }]] };
     y: genutzte Höhe, K: verfügbare Höhe (unter Kopf und Werbung, über der Fußzeile). */
  function setzen(m, modus) {
    const S = m.secs, n = S.length, G = m.G, jede = modus === 'jede' && m.fuss > 0;
    const kap = (p, res) => m.H - (p === 0 ? m.kopf1 + m.werb : m.kopf2) - (res ? m.fuss : 0);
    const balken = (s, c, forts) => (s.name ? (forts ? s.barF[c] : s.bar[c]) : 0);
    const ganz = (u) => ({ gi: u.gi, von: 0, bis: u.rows.length, forts: false, h: u.h });
    /* Zeilen eines Blocks auf Spalten mit den Zeilenhöhen „caps“ verteilen, jede Spalte im Verhältnis ihrer Höhe gefüllt
       (gleiche Höhen: gleich hohe Teile). Rückgabe: je Spalte ein Teil (auch leere) oder null, wenn nicht alles passt. */
    const stuecke = (u, caps) => {
      const ges = summe(u.rows), alle = summe(caps), out = [];
      let von = 0, acc = 0, soll = 0;
      caps.forEach((cap, k) => {
        soll += ges * cap / alle;
        let bis = von, hh = 0;
        while (bis < u.rows.length && hh + u.rows[bis] <= cap + EPS && (k === caps.length - 1 || acc + hh + u.rows[bis] / 2 <= soll)) { hh += u.rows[bis]; bis++; }
        out.push({ gi: u.gi, von, bis, forts: von > 0, h: (von > 0 ? u.headF : u.head) + hh });
        acc += hh; von = bis;
      });
      return von >= u.rows.length ? out : null;
    };

    /* Besteht der Druck aus einem einzigen Block (Einzelangebot, sortierte Gesamtliste ohne Gruppen, Auswahl aus einer Gruppe),
       wird er gleichmäßig über die drei Spalten so weniger Seiten wie möglich verteilt – sonst bliebe er in einer Spalte.
       Ab MIN_ZEILEN Zeilen je Spalte; die sortierte Gesamtliste („verteilen“) immer. */
    const u1 = n === 1 && S[0].units.length === 1 ? S[0].units[0] : null;
    if (u1 && (u1.verteilen || u1.rows.length >= SPALTEN * MIN_ZEILEN)) {
      const u = u1, s = S[0];
      for (let P = 1; P <= 400; P++) {
        const res = (p) => m.fuss > 0 && (jede || p === P - 1), caps = [];
        for (let p = 0; p < P; p++) for (let c = 0; c < SPALTEN; c++) caps.push(Math.max(0, kap(p, res(p)) - balken(s, SPALTEN, p > 0) - (caps.length ? u.headF : u.head)));
        const st = summe(caps) + EPS < summe(u.rows) ? null : stuecke(u, caps);
        if (!st) continue;
        const seiten = [];
        for (let p = 0; p < P; p++) {
          const cols = st.slice(p * SPALTEN, (p + 1) * SPALTEN).filter((x) => x.bis > x.von).map((x) => [x]);
          if (!cols.length && p > 0) continue;
          const y = cols.length ? balken(s, SPALTEN, p > 0) + Math.max(...cols.map((c) => c[0].h)) : 0;
          seiten.push({ bands: cols.length ? [{ teile: [{ si: 0, c: SPALTEN, forts: p > 0, cols }], h: y }] : [], y, K: kap(p, res(p)) });
        }
        return seiten;
      }
    }

    /* Blöcke je Bereich; nur eine Gruppe, die allein höher ist als eine ganze Seitenspalte, wird in gleich hohe Teile zerlegt */
    for (const s of S) {
      const voll = kap(1, jede) - Math.max(balken(s, SPALTEN, false), balken(s, SPALTEN, true));
      s.teile = [];
      for (const u of s.units) {
        const cap = voll - u.headF;
        let st = null;
        if (u.h > voll + EPS && cap > 0) for (let k = Math.ceil(summe(u.rows) / cap); !st && k <= u.rows.length; k++) st = stuecke(u, Array(k).fill(cap));
        s.teile.push(...(st ? st.filter((x) => x.bis > x.von) : [ganz(u)]));
      }
    }
    /* Blöcke in fester Reihenfolge ungeteilt auf c Spalten: höchste Spalte so niedrig wie möglich (wie am Bildschirm) */
    const teilen = (us, c) => {
      const k = us.length;
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
      for (let j = c, i = k; j >= 1; j--) { const a = cut[j][i]; cols.unshift(us.slice(a, i)); i = a; }
      return { h: f[c][k], cols };
    };
    const memo = new Map();
    const lage = (si, a, b, c) => { const key = si + '.' + a + '.' + b + '.' + c; if (!memo.has(key)) memo.set(key, teilen(S[si].teile.slice(a, b), c)); return memo.get(key); };
    /* Fertige Zeile aus Teilen ({ si, c, forts, cols, inhalt: Höhe der Blöcke }) mit ihrer Höhe. Wie am Bildschirm: ein Bereich
       allein in der Zeile bekommt den Balken über die ganze Breite; ein Bereich ohne Namen neben einem benannten bekommt
       einen unsichtbaren Balken, damit die Blöcke der Zeile auf gleicher Höhe beginnen. */
    const band = (teile) => {
      const allein = teile.length === 1, mitName = teile.some((t) => S[t.si].name);
      const ts = teile.map((t) => { const s = S[t.si], c = allein ? SPALTEN : t.c, leer = !s.name && mitName; return { ...t, c, leer, h: (leer ? m.leer : balken(s, c, t.forts)) + t.inhalt }; });
      return { teile: ts, h: Math.max(...ts.map((t) => t.h)) };
    };
    /* Zeile aus ganzen Bereichen ab Bereich i (ab seinem Block u0): der Bereich in 1–3 Spalten, dazu wahlweise die folgenden
       Bereiche nebeneinander (zusammen höchstens drei Spalten); frei = Spalten, die rechts noch übrig sind */
    const kmemo = new Map();
    const kandidaten = (i, u0) => {
      const key = i + '.' + u0;
      if (kmemo.has(key)) return kmemo.get(key);
      const out = [];
      const rec = (j, frei, teile) => {
        const s = S[j], v = j === i ? u0 : 0, forts = v > 0, anz = s.teile.length - v;
        for (let c = 1; c <= Math.min(frei, anz); c++) {
          const l = lage(j, v, s.teile.length, c), t = teile.concat({ si: j, c, forts, cols: l.cols, inhalt: l.h });
          out.push({ teile: t, band: band(t), bis: j + 1, frei: frei - c });
          if (j + 1 < n && frei - c >= 1) rec(j + 1, frei - c, t);
        }
      };
      rec(i, SPALTEN, []);
      kmemo.set(key, out);
      return out;
    };

    /* Eine Seite füllen ab Stand st ({ i: Bereich, u: Block }); res: Platz für die Fußzeile freihalten.
       Gesucht ist der weiteste Stand, den die Seite erreicht (bei gleichem Stand die geringste Höhe): Zeilen aus ganzen
       Bereichen, am Ende wahlweise ein angefangener Bereich (Balken und mindestens ein Block) in den freien Spalten. */
    const seite = (st, p, res) => {
      const K = kap(p, res), best = new Map([[st.i, { y: 0, bands: [] }]]);
      let offen = null;   // weitester Stand mit Umbruch im Bereich
      for (let i = st.i; i < n; i++) {
        const z = best.get(i);
        if (!z) continue;
        const u0 = i === st.i ? st.u : 0, lueck = z.bands.length ? m.BAND : 0, R = K - z.y - lueck;
        const ks = kandidaten(i, u0);
        for (const k of ks) {
          const y = z.y + lueck + k.band.h, alt = best.get(k.bis);
          if (k.band.h <= R + EPS && (!alt || y < alt.y - EPS)) best.set(k.bis, { y, bands: z.bands.concat(k.band) });
        }
        for (const pre of [{ teile: [], bis: i, frei: SPALTEN }].concat(ks.filter((k) => k.frei >= 1 && k.bis < n && k.band.h <= R + EPS))) {
          const j = pre.bis, s = S[j], v = j === i ? u0 : 0;
          let a = v, b = null;
          for (let e = v + 1; e < s.teile.length; e++) {
            const l = lage(j, v, e, pre.frei), x = band(pre.teile.concat({ si: j, c: pre.frei, forts: v > 0, cols: l.cols, inhalt: l.h }));
            if (x.h > R + EPS) break;
            a = e; b = x;
          }
          if (!b) continue;
          const w = { i: j, u: a, y: z.y + lueck + b.h, bands: z.bands.concat(b) };
          if (!offen || w.i > offen.i || (w.i === offen.i && (w.u > offen.u || (w.u === offen.u && w.y < offen.y - EPS)))) offen = w;
        }
      }
      const fertig = Math.max(...best.keys());
      return offen && offen.i >= fertig ? offen : { i: fertig, u: fertig === st.i ? st.u : 0, y: best.get(fertig).y, bands: best.get(fertig).bands };
    };

    /* Ab Stand st0 auf Seite p0 alle Seiten füllen; res(p): auf Seite p Platz für die Fußzeile freihalten */
    const lauf = (st0, p0, res) => {
      const seiten = [], starts = [];
      let st = st0;
      for (let p = p0; (st.i < n || p === p0) && p < p0 + 400; p++) {
        starts.push(st);
        const steht = (e) => e.i === st.i && e.u === st.u;
        let frei = res(p), e = seite(st, p, frei);
        if (steht(e) && frei && st.i < n) { frei = false; e = seite(st, p, false); }   // der nächste Block passt nur ohne Fußzeile auf eine Seite
        if (steht(e) && p > 0 && st.i < n) {   // passt auf keine Seite (z. B. sehr hoher Kopf): trotzdem setzen, damit es weitergeht
          const s = S[st.i], b = band([{ si: st.i, c: SPALTEN, forts: st.u > 0, cols: [[s.teile[st.u]]], inhalt: s.teile[st.u].h }]);
          e = { i: st.u + 1 >= s.teile.length ? st.i + 1 : st.i, u: st.u + 1 >= s.teile.length ? 0 : st.u + 1, y: b.h, bands: [b] };
        }
        seiten.push({ bands: e.bands, y: e.y, K: kap(p, frei), res: frei });
        st = { i: e.i, u: e.u };
      }
      return { seiten, starts };
    };
    const L = lauf({ i: 0, u: 0 }, 0, () => jede);
    let seiten = L.seiten;
    const p = seiten.length - 1;
    if (!jede && m.fuss > 0 && seiten[p].y + m.fuss > seiten[p].K + EPS) {
      // Fußzeile passt nicht mehr unter die letzte Seite: diese Seite mit freigehaltenem Fuß neu setzen (der Rest wandert weiter)
      seiten = seiten.slice(0, p).concat(lauf(L.starts[p], p, () => true).seiten);
      if (!seiten[seiten.length - 1].res) seiten.push({ bands: [], y: 0, K: kap(seiten.length, true), res: true });   // Fußzeile allein
    }
    seiten.forEach((s, q) => { s.K = kap(q, m.fuss > 0 && (jede || q === seiten.length - 1)); });   // verfügbare Höhe, wie die Seite gedruckt wird
    return seiten;
  }

  /* cfg: { host (#print-root), bereiche: [{ name, balken(forts), gruppen: [{ n, block(von, bis, forts), verteilen? }] }],
            kopf(seite, seiten), werbung?, fuss?: {spalten, zeilen}, hinweis?: [Zeilen], modus: 'letzte' | 'jede', stufe?: Name einer Stufe }
     Rückgabe { html, seiten, spalten, geteilt, stufe, fuell: [Füllgrad je Seite in %] } – html ersetzt den Inhalt von host. */
  function liste(cfg) {
    const host = cfg.host, modus = cfg.modus === 'jede' ? 'jede' : 'letzte';
    const fuss = fussHTML(cfg.fuss, cfg.hinweis, 'quer');
    const fest = STUFEN.filter((s) => s.name === cfg.stufe), alt = host.innerHTML;
    let wahl = null;
    host.classList.add('pl-messen');
    try {
      // größte Schrift, mit der es nicht mehr Seiten werden als mit der kleinsten
      for (const st of fest.length ? fest : STUFEN) { const seiten = setzen(messen(host, cfg, fuss, st), modus); if (!wahl || seiten.length < wahl.seiten.length) wahl = { st, seiten }; }
    } finally { host.classList.remove('pl-messen'); host.innerHTML = alt; }
    const { st, seiten } = wahl, N = seiten.length;
    let geteilt = 0, bereichForts = 0;
    const band = (b) => `<div class="al-band">${b.teile.map((t) => {
      const ber = cfg.bereiche[t.si];
      if (t.forts && ber.name) bereichForts++;
      const cols = t.cols.concat(Array(Math.max(0, t.c - t.cols.length)).fill([]));   // weniger Blöcke als Spalten: die übrigen bleiben frei
      return `<section class="al-sec" style="--c:${t.c}">${ber.name ? ber.balken(t.forts) : t.leer ? LEER : ''}
        <div class="al-cols" style="--k:${t.c}">${cols.map((col) => `<div class="al-col">${col.map((fr) => { if (fr.forts) geteilt++; return ber.gruppen[fr.gi].block(fr.von, fr.bis, fr.forts); }).join('')}</div>`).join('')}</div></section>`;
    }).join('')}</div>`;
    const fuell = seiten.map((s) => Math.round(100 * Math.min(1, s.y / Math.max(1, s.K))));
    const html = seiten.map((s, p) => `<section class="pl-page" data-fuell="${fuell[p]}"><div class="pl-in">${cfg.kopf(p + 1, N)}${p === 0 ? cfg.werbung || '' : ''}
      ${s.bands.map(band).join('')}${fuss && (modus === 'jede' || p === N - 1) ? fuss : ''}</div></section>`).join('');
    return { html: `<div class="al al-print pl-doc pl-${st.name}" style="--z:${zFaktor(st)}" data-seiten="${N}" data-spalten="${SPALTEN}" data-stufe="${st.name}" data-fuss="${fuss ? modus : 'ohne'}" data-geteilt="${geteilt}" data-bereich-forts="${bereichForts}">${html}</div>`,
      seiten: N, spalten: SPALTEN, geteilt, stufe: st.name, fuell };
  }

  root.AngebotDruck = { liste, fussHTML, SEITE, STUFEN };
})(window);
