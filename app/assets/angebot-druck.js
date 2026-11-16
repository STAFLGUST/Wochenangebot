/* Angebot · Satz der Druckfassung „Angebotsansicht“ (A4) für die Angebotsseite (frontend.js, Wunsch des Inhabers 13.11.2026).
   Der Druck sieht aus wie die Vorschau (Angebotsansicht am Bildschirm): Kopf mit Logo und Titel, Bereiche als abgerundete
   Balken über den Spalten ihres Bereichs, Gruppen als Blöcke mit „€/kg“, abgerundete gestreifte Zeilen. Ohne Design drei
   Spalten quer; das Design des Angebots (Inhaber 16.11.2026, cfg.raster und je Bereich k/ab) legt Format (quer/hoch) und
   Spalten je Abschnitt fest (im Hochformat höchstens drei) – Bereiche verschiedener Abschnitte stehen nie in einer Zeile, ein
   fester Block (fest: fertiges HTML, z. B. Text-Abschnitt oder Überschrift) steht über die ganze Breite und wird nie geteilt.
   Heißt die einzige Gruppe eines Bereichs wie der Bereich (kopfImBalken) und steht der Bereich in einer Spalte, trägt sein
   Balken „€/kg“ und der Block keinen eigenen Kopf (keine doppelte Überschrift; am Bildschirm bleibt der Kopf).
   Wochenangebot, Kundenangebote und Einzelangebote nutzen denselben Satz. Regeln:
   - Ein Block (Gruppe mit Kopf und allen Zeilen) steht immer vollständig in einer Spalte auf einer Seite.
   - Die Seiten werden fortlaufend gefüllt: jede Seite nimmt so viele Blöcke auf wie möglich. Die Blöcke eines Bereichs
     stehen in der Reihenfolge des Angebots nebeneinander in möglichst gleich hohen Spalten (links oben der erste Block);
     kleine Bereiche stehen nebeneinander in einer Zeile, wenn das Höhe spart. Folgen mehr Bereiche mit Namen, als die Zeile
     Spalten hat, mit höchstens zwei Blöcken (STAPEL_BLOECKE), dürfen sie als Stapel stehen: jeder einspaltig, in Reihenfolge von oben nach unten auf die Spalten verteilt –
     so füllen kurze Bereiche die Lücke unter ihrem Vorgänger, statt dass der höchste Nachbar die Zeile bestimmt
     (Wunsch des Inhabers 16.11.2026: weniger freie Flächen im Druck).
   - Ein Bereich beginnt auf der laufenden Seite, sobald sein Balken und mindestens ein ganzer Block Platz haben. Umbrochen
     wird nur zwischen Blöcken; auf der nächsten Seite steht der Balken noch einmal („Forts.“).
   - Einzige Ausnahme vom ungeteilten Block: eine Gruppe, die allein höher ist als eine ganze Seitenspalte, wird in gleich
     hohe Teile zerlegt (Gruppenkopf mit „Forts.“), die wie Blöcke gesetzt werden. Die sortierte Gesamtliste ohne Gruppen
     („verteilen“) wird gleichmäßig auf die Spalten jeder Seite verteilt.
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
  const SEITEN = { quer: SEITE, hoch: { b: 192, h: 280 } };   // hoch: 210 × 297 mit denselben Rändern
  const SPALTEN = 3;                          // ohne Design drei Spalten (Wunsch des Inhabers)
  /* Stufen der Dichte, von groß nach klein: Satzbreite in px der Bildschirmansicht (13 px Schrift werden im Druck
     8,3 / 7,9 / 7,5 pt); Zeilenhöhe und Abstände je Stufe stehen in angebot-druck.css (.pl-normal, .pl-kompakt, .pl-eng) */
  const STUFEN = [{ name: 'normal', breite: 1240 }, { name: 'kompakt', breite: 1310 }, { name: 'eng', breite: 1370 }];
  const STAPEL_BLOECKE = 2;                   // im Stapel nur kleine Bereiche: höchstens so viele Blöcke (größere bleiben über ihre Spalten verteilt)
  const MIN_ZEILEN = 3;                       // ein einzelner Block wird erst ab so vielen Zeilen je Spalte über die Spalten verteilt
  const EPS = 0.5;                            // px Toleranz beim Vergleichen gemessener Höhen
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
  const TRENN = '<div class="al-st pl-trenn" aria-hidden="true"><h3>&nbsp;</h3></div>';   // Bereich ohne Namen zwischen benannten: Linie in der Höhe eines Balkens – er gehört sichtbar zu keinem Nachbarn
  const zeilen = (t) => String(t ?? '').split('\n').map((l) => l.trim()).filter(Boolean);
  const summe = (a) => a.reduce((x, y) => x + y, 0);
  /* Verkleinerung der Satzfläche auf den Satzspiegel (px der Bildschirmansicht → A4); 1 mm = 96/25,4 px. Gleicher Faktor im
     Hochformat: die Satzfläche ist dort schmaler (Breite des Satzspiegels / z), die Schrift gleich groß. */
  const zFaktor = (st) => Math.round(SEITE.b * 96 / 25.4 / st.breite * 100000) / 100000;

  /* Fußzeile des Briefbogens: Siegel links, daneben die Textspalten gleich breit und oben bündig, darunter über dieselbe
     Breite die Registerzeilen (Handelsregister, Geschäftsführung) kleiner; darüber der Hinweis (Mengen, Fracht).
     art „quer“ (Angebotsansicht) und „hoch“ (Kompakt, Tabelle) sind gleich aufgebaut, nur die Maße unterscheiden sich.
     Schreibweise nur für die Anzeige geordnet (gespeicherte Texte bleiben unverändert): „ * “ als Trenner wird „ · “,
     kein Leerzeichen vor Doppelpunkt und innerhalb von Klammern – so wie im Briefbogen gemeint, aber ruhiger zu lesen. */
  const ordnen = (t) => String(t).replace(/\s*\*\s*/g, ' · ').replace(/\s+:/g, ':').replace(/\(\s+/g, '(').replace(/\s+\)/g, ')');
  function fussHTML(fuss, hinweis, art) {
    const f = fuss || {}, sp = Array.isArray(f.spalten) ? f.spalten : [], ze = (Array.isArray(f.zeilen) ? f.zeilen : []).filter((z) => String(z || '').trim());
    const hin = (hinweis || []).filter((l) => String(l || '').trim());
    const spalten = sp.map((t) => zeilen(t)).filter((l) => l.length);
    if (!spalten.length && !ze.length && !hin.length) return '';
    const brief = spalten.length || ze.length ? `<div class="pl-brief"><img class="pl-siegel" src="assets/druck-siegel.jpg" width="316" height="250" alt="">
        <div class="pl-btext">${spalten.length ? `<div class="pl-bsp" style="--n:${spalten.length}">${spalten.map((l) => `<p class="pl-bs">${l.map((z) => esc(ordnen(z))).join('<br>')}</p>`).join('')}</div>` : ''}
        ${ze.length ? `<p class="pl-bz">${ze.map((z) => `<span>${esc(ordnen(z))}</span>`).join('')}</p>` : ''}</div></div>` : '';
    return `<footer class="pl-fuss pl-fuss-${art === 'hoch' ? 'hoch' : 'quer'}">${hin.length ? `<p class="pl-hinweis">${hin.map((l, i) => `<span${i === 0 ? ' class="lead"' : ''}>${esc(l)}</span>`).join(' ')}</p>`.replace(/([^.!?:;…])<\/span> <span/g, '$1</span> · <span') : ''}${brief}</footer>`;
  }

  /* ---------- Messen: Bausteine unsichtbar in Druckgröße setzen (eine Stufe) ----------
     Höhen in px der Satzfläche, Abstände eingeschlossen (Balken mit seinem Abstand nach unten, Kopf mit seinem Abstand).
     Die Abstände zwischen Blöcken und Zeilen von Bereichen stehen nur in angebot-druck.css (--ab-gruppe, --ab-band). */
  function messen(host, cfg, fuss, st, css) {
    let col = '', balken = '';
    cfg.bereiche.forEach((b, bi) => {
      const K = b.k, cs = Array.from({ length: K }, (_, i) => i + 1);
      if (b.fest) { balken += `<div class="pl-m pl-mb" data-t="${bi}" style="--c:${K};--k:${K}">${festHTML(b)}</div>`; return; }
      if (b.name) balken += cs.map((c) => `<div class="pl-m pl-mb" data-b="${bi}.${c}" style="--c:${c};--k:${K}">${b.balken(false)}</div><div class="pl-m pl-mb" data-bf="${bi}.${c}" style="--c:${c};--k:${K}">${b.balken(true)}</div>`).join('');
      let c1 = '';
      if (b.kopfImBalken) { balken += `<div class="pl-m pl-mb" data-be="${bi}" style="--c:1;--k:${K}">${b.balken(false, true)}</div>`; c1 += `<div data-o="${bi}" class="pl-m">${b.gruppen[0].block(0, b.gruppen[0].n, false, true)}</div>`; }
      b.gruppen.forEach((g, gi) => { c1 += `<div data-g="${bi}.${gi}" class="pl-m">${g.block(0, g.n, false)}</div><div data-f="${bi}.${gi}" class="pl-m">${g.block(0, 1, true)}</div>`; });
      col += `<div class="pl-mcol" style="--k:${K}">${c1}</div>`;
    });
    host.innerHTML = `<div class="al al-print pl-doc pl-mess pl-${st.name}" style="${css}"><div class="pl-in">
      <div data-m="mm" style="height:100mm"></div>
      <div data-m="kopf1" class="pl-m">${cfg.kopf(1, 1)}</div><div data-m="kopf2" class="pl-m">${cfg.kopf(2, 2)}</div>
      <div data-m="werb" class="pl-m">${cfg.werbung || ''}</div><div data-m="fuss" class="pl-m">${fuss}</div><div data-m="trenn" class="pl-m pl-mb" style="--c:1">${TRENN}</div>
      ${balken}${col}</div></div>`;
    const h = (el) => (el ? el.getBoundingClientRect().height : 0);
    const q = (s) => host.querySelector(s);
    const stil = getComputedStyle(q('.pl-doc')), ab = (n) => parseFloat(stil.getPropertyValue('--ab-' + n)) || 0;
    const secs = cfg.bereiche.map((b, bi) => {
      const bar = Array(b.k + 1).fill(0), barF = Array(b.k + 1).fill(0), basis = { k: b.k, ab: b.ab };
      if (b.fest) { const th = h(q(`[data-t="${bi}"]`)); return { ...basis, name: false, fest: true, kopf: !!b.kopf, bar, barF, units: [{ gi: 0, h: th, head: th, headF: th, rows: [], fest: true }], eh: null }; }
      if (b.name) for (let c = 1; c <= b.k; c++) { bar[c] = h(q(`[data-b="${bi}.${c}"]`)); barF[c] = h(q(`[data-bf="${bi}.${c}"]`)); }
      const units = b.gruppen.map((g, gi) => {
        const box = q(`[data-g="${bi}.${gi}"]`), boxF = q(`[data-f="${bi}.${gi}"]`);
        const rows = [...box.querySelector('table').tBodies[0].rows].map((r) => r.getBoundingClientRect().height);
        const head = h(box) - summe(rows);   // Gruppenkopf samt Linien
        return { gi, h: h(box), head, headF: Math.max(head, h(boxF) - h(boxF.querySelector('table').tBodies[0].rows[0])), rows, verteilen: !!g.verteilen };   // headF: Kopf mit „Forts.“
      });
      const eh = b.name && b.kopfImBalken ? { bar: h(q(`[data-be="${bi}"]`)), weniger: units[0].h - h(q(`[data-o="${bi}"]`)) } : null;   // „€/kg“ im Balken, Block ohne Kopf
      return { ...basis, name: !!b.name, bar, barF, units, eh };
    });
    return { H: cfg.seite.h * h(q('[data-m="mm"]')) / 100 / zFaktor(st), secs, kopf1: h(q('[data-m="kopf1"]')), kopf2: h(q('[data-m="kopf2"]')), werb: h(q('[data-m="werb"]')),
      fuss: fuss ? h(q('[data-m="fuss"]')) : 0, trenn: h(q('[data-m="trenn"]')), G: ab('gruppe'), BAND: ab('band') };
  }

  /* ---------- Verteilen ----------
     Rückgabe: Seiten [{ bands, y, K }] – bands: Zeilen der Seite, jede mit „teile“ (ein Bereich in 1–3 Spalten oder mehrere
     Bereiche nebeneinander, zusammen drei Spalten): { si: Bereich, c: Spalten, forts, trenn, cols: [[{ gi, von, bis, forts, h }]] },
     oder ein Stapel mit „stapel“: drei Spalten, jede eine Liste solcher Teile (c = 1) untereinander; ein Teil mit eh trägt
     „€/kg“ im Balken (Block ohne Kopf); y: genutzte Höhe, K: verfügbare Höhe (unter Kopf und Werbung, über der Fußzeile). */
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
       wird er gleichmäßig über die Spalten so weniger Seiten wie möglich verteilt – sonst bliebe er in einer Spalte.
       Ab MIN_ZEILEN Zeilen je Spalte; die sortierte Gesamtliste („verteilen“) immer. Führende Überschriften (kopf) stehen auf
       Seite 1 über die ganze Breite darüber; ihre Höhe fehlt dort jeder Spalte. */
    let v1 = 0;
    while (v1 < n - 1 && S[v1].kopf) v1++;
    const u1 = n === v1 + 1 && S[v1].units.length === 1 && !S[v1].fest ? S[v1].units[0] : null;
    if (u1 && (u1.verteilen || u1.rows.length >= S[v1].k * MIN_ZEILEN)) {
      const u = u1, s = S[v1], K = s.k;
      const koepfe = S.slice(0, v1).map((x, si) => ({ teile: [{ si, c: x.k }], h: x.units[0].h, k: x.k }));
      const oben = summe(koepfe.map((b) => b.h + m.BAND));   // Überschriften samt Zeilenabstand darunter
      for (let P = 1; P <= 400; P++) {
        const res = (p) => m.fuss > 0 && (jede || p === P - 1), caps = [];
        for (let p = 0; p < P; p++) for (let c = 0; c < K; c++) caps.push(Math.max(0, kap(p, res(p)) - (p === 0 ? oben : 0) - balken(s, K, p > 0) - (caps.length ? u.headF : u.head)));
        const st = summe(caps) + EPS < summe(u.rows) ? null : stuecke(u, caps);
        if (!st) continue;
        const seiten = [];
        for (let p = 0; p < P; p++) {
          const cols = st.slice(p * K, (p + 1) * K).filter((x) => x.bis > x.von).map((x) => [x]);
          if (!cols.length && p > 0) continue;
          const block = cols.length ? [{ teile: [{ si: v1, c: K, forts: p > 0, cols }], h: balken(s, K, p > 0) + Math.max(...cols.map((c) => c[0].h)), k: K }] : [];
          const bands = (p === 0 ? koepfe : []).concat(block);
          seiten.push({ bands, y: summe(bands.map((b) => b.h)) + m.BAND * Math.max(0, bands.length - 1), K: kap(p, res(p)) });
        }
        return seiten;
      }
    }

    /* Blöcke je Bereich; nur eine Gruppe, die allein höher ist als eine ganze Seitenspalte (voll), wird in gleich hohe Teile
       zerlegt – so hoch, dass sie auch unter Kopf und Werbung der ersten Seite passen, solange dort die halbe Höhe frei ist */
    for (const s of S) {
      const bar = Math.max(balken(s, s.k, false), balken(s, s.k, true)), voll = kap(1, jede) - bar;
      s.teile = [];
      for (const u of s.units) {
        const cap = Math.min(voll, Math.max(kap(0, jede) - bar, voll / 2)) - u.headF;
        let st = null;
        if (!u.fest && u.h > voll + EPS && cap > 0) for (let k = Math.ceil(summe(u.rows) / cap); !st && k <= u.rows.length; k++) st = stuecke(u, Array(k).fill(cap));
        s.teile.push(...(st ? st.filter((x) => x.bis > x.von) : [ganz(u)]));
      }
    }
    /* Einheiten mit Höhe h in fester Reihenfolge ungeteilt auf c Spalten, g Abstand dazwischen: höchste Spalte so niedrig wie
       möglich (wie am Bildschirm). Einheiten sind die Blöcke eines Bereichs (Abstand G) oder ganze Bereiche eines Stapels. */
    const teilen = (us, c, g = G) => {
      const k = us.length;
      c = Math.max(1, Math.min(c, k));
      const pre = [0];
      for (const u of us) pre.push(pre[pre.length - 1] + u.h);
      const hoehe = (a, i) => pre[i] - pre[a] + g * (i - a - 1);
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
    /* Fertige Zeile aus Teilen ({ si, c, forts, cols, inhalt: Höhe der Blöcke }) mit ihrer Höhe. Jede Zeile ist genau so breit,
       wie ihr Abschnitt Spalten hat (k): der letzte Bereich der Zeile bekommt die Spalten, die rechts übrig sind (sein Balken reicht bis zum Rand;
       ein Bereich allein also über die ganze Breite, wie am Bildschirm). Ein Bereich ohne Namen trägt statt des Balkens eine
       Linie in derselben Höhe, wenn andere Bereiche Namen haben (hatNamen): seine Blöcke beginnen bündig mit denen der
       Nachbarn, gehören aber sichtbar nicht zu deren Balken. */
    const hatNamen = S.some((s) => s.name);
    // Teil mit seiner Höhe: Balken bzw. Linie und Inhalt; „€/kg“ im Balken nur, wenn der Bereich ungeteilt in einer Spalte steht
    const fertig = (t, c = t.c) => {
      const s = S[t.si], trenn = !s.name && !s.fest && hatNamen, eh = !!s.eh && c === 1 && s.teile.length === 1;
      return { ...t, c, trenn, eh, h: (trenn ? m.trenn : eh ? s.eh.bar : balken(s, c, t.forts)) + t.inhalt - (eh ? s.eh.weniger : 0) };
    };
    const band = (teile) => {
      const K = S[teile[0].si].k, rest = K - teile.reduce((x, t) => x + t.c, 0);
      const ts = teile.map((t, k) => fertig(t, t.c + (k === teile.length - 1 ? rest : 0)));
      return { teile: ts, h: Math.max(...ts.map((t) => t.h)), k: K };
    };
    /* Zeile aus ganzen Bereichen ab Bereich i (ab seinem Block u0): der Bereich in 1–K Spalten, dazu wahlweise die folgenden
       Bereiche desselben Abschnitts nebeneinander (zusammen höchstens K Spalten); frei = Spalten, die rechts noch übrig sind.
       Ein fester Block steht allein über alle K Spalten. */
    const kmemo = new Map();
    const kandidaten = (i, u0) => {
      const key = i + '.' + u0;
      if (kmemo.has(key)) return kmemo.get(key);
      const out = [], K = S[i].k, ab = S[i].ab;
      const rec = (j, frei, teile) => {
        const s = S[j], v = j === i ? u0 : 0, forts = v > 0, anz = s.teile.length - v;
        for (let c = s.fest ? frei : 1; c <= (s.fest ? frei : Math.min(frei, anz)); c++) {
          const l = lage(j, v, s.teile.length, c), t = teile.concat({ si: j, c, forts, cols: l.cols, inhalt: l.h });
          out.push({ teile: t, band: band(t), bis: j + 1, frei: frei - c });
          if (j + 1 < n && frei - c >= 1 && S[j + 1].ab === ab) rec(j + 1, frei - c, t);
        }
      };
      rec(i, K, []);
      /* Stapel ab Bereich i: mehr als K ganze Bereiche mit Namen, jeder in einer Spalte, untereinander mit dem Abstand der
         Zeilen. Ohne „teile“: ein Stapel wird nie um einen angefangenen Bereich ergänzt (seite). Höher als K Seitenspalten
         passt er nie – dort endet die Suche (sonst wächst die Rechenzeit mit der Zahl der Bereiche stark). */
      const reihe = [];
      let hoch = 0;
      for (let j = i; j < n && S[j].ab === ab && S[j].name && S[j].teile.length - (j === i ? u0 : 0) <= STAPEL_BLOECKE; j++) {
        const v = j === i ? u0 : 0, l = lage(j, v, S[j].teile.length, 1), t = fertig({ si: j, c: 1, forts: v > 0, cols: l.cols, inhalt: l.h });
        reihe.push(t);
        if ((hoch += t.h) > K * m.H) break;
        if (reihe.length > K) { const sp = teilen(reihe, K, m.BAND); out.push({ band: { stapel: sp.cols, h: sp.h, k: K }, bis: j + 1, frei: 0 }); }
      }
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
        for (const pre of [{ teile: [], bis: i, frei: S[i].k }].concat(ks.filter((k) => k.teile && k.frei >= 1 && k.bis < n && S[k.bis].ab === S[i].ab && k.band.h <= R + EPS))) {
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
      // eine Überschrift (kopf) bleibt bei ihrem Abschnitt: die Seite endet nie direkt nach ihr
      const fertig = Math.max(...[...best.keys()].filter((k) => k === st.i || k >= n || !S[k - 1].kopf));
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
        if (steht(e) && frei && !jede && st.i < n) { frei = false; e = seite(st, p, false); }   // „letzte“: der nächste Block passt nur ohne Fußzeile auf eine Seite
        if (steht(e) && p > 0 && st.i < n) {   // passt auf keine Seite (z. B. sehr hoher Kopf): trotzdem setzen, damit es weitergeht
          const s = S[st.i], b = band([{ si: st.i, c: s.k, forts: st.u > 0, cols: [[s.teile[st.u]]], inhalt: s.teile[st.u].h }]);
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

  /* Fester Block über die ganze Breite: fertiges HTML (Text-Abschnitt des Designs, von frontend.js escaped) */
  const festHTML = (b, c) => `<section class="al-sec pl-fest"${c ? ` style="--c:${c}"` : ''}>${b.fest}</section>`;

  /* cfg: { host (#print-root), raster?: { spalten 1–4, format 'quer' | 'hoch' } (ohne: drei Spalten quer; hoch: höchstens drei),
            bereiche: [{ name, kopfImBalken?, balken(forts, eh), gruppen: [{ n, block(von, bis, forts, ohneKopf), verteilen? }], k?, ab? }
                       | { fest: HTML eines unteilbaren Blocks über die ganze Breite, kopf?, k?, ab? }] – kopf: Überschrift, die mit dem folgenden Abschnitt auf die Seite kommt; k: Spalten des Abschnitts (Vorgabe raster.spalten), ab: Abschnitt (Bereiche
                       verschiedener Abschnitte stehen nie in einer Zeile; ohne Angabe alle in einem),
            kopf(seite, seiten), werbung?, fuss?: {spalten, zeilen}, hinweis?: [Zeilen], modus: 'letzte' | 'jede', stufe?: Name einer Stufe }
     Rückgabe { html, seiten, spalten, format, geteilt, stufe, fuell: [Füllgrad je Seite in %] } – html ersetzt den Inhalt von host. */
  function liste(cfg0) {
    const format = cfg0.raster && cfg0.raster.format === 'hoch' ? 'hoch' : 'quer', seite = SEITEN[format];
    const KMAX = format === 'hoch' ? 3 : 4;   // im Hochformat würden vier Spalten die Bezeichnungen Buchstabe für Buchstabe umbrechen
    const K0 = Math.min(KMAX, cfg0.raster && cfg0.raster.spalten >= 1 && cfg0.raster.spalten <= 4 ? cfg0.raster.spalten : SPALTEN);
    const cfg = { ...cfg0, seite, bereiche: cfg0.bereiche.map((b) => ({ ...b, k: Math.min(KMAX, b.k >= 1 && b.k <= 4 ? b.k : K0), ab: b.ab ?? 0 })) };
    const host = cfg.host, modus = cfg.modus === 'jede' ? 'jede' : 'letzte';
    const stil = (st) => `--z:${zFaktor(st)}` + (format === 'hoch' ? `;--sb:${seite.b}mm;--sh:${seite.h}mm` : '');
    const fuss = fussHTML(cfg.fuss, cfg.hinweis, 'quer');
    const fest = STUFEN.filter((s) => s.name === cfg.stufe), alt = host.innerHTML;
    let wahl = null;
    host.classList.add('pl-messen');
    try {
      // größte Schrift, mit der es nicht mehr Seiten werden als mit der kleinsten
      for (const st of fest.length ? fest : STUFEN) { const seiten = setzen(messen(host, cfg, fuss, st, stil(st)), modus); if (!wahl || seiten.length < wahl.seiten.length) wahl = { st, seiten }; }
    } finally { host.classList.remove('pl-messen'); host.innerHTML = alt; }
    const { st, seiten } = wahl, N = seiten.length;
    let geteilt = 0, bereichForts = 0;
    const sec = (t) => {
      const ber = cfg.bereiche[t.si];
      if (ber.fest) return festHTML(ber, t.c);
      if (t.forts && ber.name) bereichForts++;
      const cols = t.cols.concat(Array(Math.max(0, t.c - t.cols.length)).fill([]));   // weniger Blöcke als Spalten: die übrigen bleiben frei
      return `<section class="al-sec" style="--c:${t.c}">${ber.name ? ber.balken(t.forts, t.eh) : t.trenn ? TRENN : ''}
        <div class="al-cols" style="--k:${t.c}">${cols.map((col) => `<div class="al-col">${col.map((fr) => { if (fr.forts) geteilt++; return ber.gruppen[fr.gi].block(fr.von, fr.bis, fr.forts, t.eh); }).join('')}</div>`).join('')}</div></section>`;
    };
    const band = (b) => (b.stapel ? `<div class="al-band al-stapel" style="--k:${b.k}">${b.stapel.map((sp) => `<div class="al-stapel-sp">${sp.map(sec).join('')}</div>`).join('')}</div>`
      : `<div class="al-band" style="--k:${b.k}">${b.teile.map(sec).join('')}</div>`);
    const fuell = seiten.map((s) => Math.round(100 * Math.min(1, s.y / Math.max(1, s.K))));
    const html = seiten.map((s, p) => `<section class="pl-page" data-fuell="${fuell[p]}"><div class="pl-in">${cfg.kopf(p + 1, N)}${p === 0 ? cfg.werbung || '' : ''}
      ${s.bands.map(band).join('')}${fuss && (modus === 'jede' || p === N - 1) ? fuss : ''}</div></section>`).join('');
    return { html: `<div class="al al-print pl-doc pl-${st.name}" style="${stil(st)}" data-seiten="${N}" data-spalten="${K0}" data-format="${format}" data-stufe="${st.name}" data-fuss="${fuss ? modus : 'ohne'}" data-geteilt="${geteilt}" data-bereich-forts="${bereichForts}">${html}</div>`,
      seiten: N, spalten: K0, format, geteilt, stufe: st.name, fuell };
  }

  root.AngebotDruck = { liste, fussHTML, SEITE, STUFEN };
})(window);
