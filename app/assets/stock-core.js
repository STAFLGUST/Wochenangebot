/* ==========================================================================
   Bestand – Einlesen der WinAB-Bestandsliste („Partieliste … verfügbar“)
   Liest .xls (BIFF2–BIFF8, auch im OLE-Container) und .xlsx.
   Berücksichtigt werden nur Zeilen mit Status „eingelagert“.
   Je Artikel: verfügbare Menge (Summe netto), frühestes MHD, Menge zum frühesten MHD.
   ========================================================================== */
(function (root) {
  'use strict';

  /* ---------- Warengruppen nach Artikelnummer ---------- */
  const WARENGRUPPEN = [
    [10000, 11899, 'Rindfleisch, frisch'], [11900, 11999, 'Kalbfleisch, frisch'],
    [20000, 20999, 'Schweinefleisch, frisch'], [30000, 30199, 'Lammfleisch, frisch'],
    [40000, 40999, 'Wild, frisch'], [45000, 45999, 'Geflügel, frisch'],
    [48000, 48200, 'Bison & Exoten, frisch'], [49535, 49700, 'Wurstwaren'],
    [50000, 50100, 'Pferdefleisch, frisch'], [60000, 61899, 'Rindfleisch, gefroren'],
    [61900, 61999, 'Kalbfleisch, gefroren'], [70000, 71000, 'Schweinefleisch, gefroren'],
    [80000, 80499, 'Lammfleisch, gefroren'], [90000, 91000, 'Wild, gefroren'],
    [95000, 95300, 'Geflügel, gefroren'], [95370, 99099, 'Exoten, gefroren'],
    [99500, 99514, 'Seafood, gefroren'],
  ];
  const OTHER_GROUP = { order: 999, label: 'Weitere Artikel', from: null, to: null };
  function warengruppe(code) {
    const s = String(code ?? '');
    if (!/^\d+$/.test(s)) return OTHER_GROUP;
    const n = Number(s);
    const i = WARENGRUPPEN.findIndex(([a, b]) => n >= a && n <= b);
    return i < 0 ? OTHER_GROUP : { order: i, label: WARENGRUPPEN[i][2], from: WARENGRUPPEN[i][0], to: WARENGRUPPEN[i][1] };
  }
  /* Artikelnummern vergleichbar machen (führende Nullen ignorieren) */
  const normCode = (c) => { const s = String(c ?? '').trim(); return /^\d+$/.test(s) ? (s.replace(/^0+/, '') || '0') : s.toUpperCase(); };

  /* ======================= .xls (BIFF) ======================= */
  function u16(b, o) { return b[o] | (b[o + 1] << 8); }
  function u32(b, o) { return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0; }
  function f64(b, o) { return new DataView(b.buffer, b.byteOffset + o, 8).getFloat64(0, true); }
  function rk(v) {
    let n;
    if (v & 2) n = (v >> 2); // 30-Bit-Ganzzahl (vorzeichenbehaftet)
    else {
      const buf = new Uint8Array(8);
      const dv = new DataView(buf.buffer);
      dv.setUint32(4, v & 0xfffffffc, true);
      n = dv.getFloat64(0, true);
    }
    return v & 1 ? n / 100 : n;
  }

  /* OLE-/CFB-Container: Datenstrom „Workbook“ bzw. „Book“ herauslösen */
  function cfbStream(b) {
    const shift = u16(b, 0x1e), size = 1 << shift, miniSize = 1 << u16(b, 0x20);
    const sec = (id) => 512 + id * size;
    if (size > 65536 || size < 128) throw new Error('Unbekanntes Dateiformat.');
    const difat = [];
    for (let i = 0; i < 109; i++) difat.push(u32(b, 0x4c + i * 4));
    let next = u32(b, 0x44), guard = 0;
    while (next < 0xfffffffa && guard++ < 10000) {
      const o = sec(next);
      for (let i = 0; i < size / 4 - 1; i++) difat.push(u32(b, o + i * 4));
      next = u32(b, o + size - 4);
    }
    const fat = [];
    for (const id of difat) {
      if (id >= 0xfffffffa) continue;
      const o = sec(id);
      if (o + size > b.length) break;
      for (let i = 0; i < size / 4; i++) fat.push(u32(b, o + i * 4));
    }
    const chain = (start, table) => {
      const out = [];
      let id = start, n = 0;
      while (id < 0xfffffffa && n++ < 1e6) { out.push(id); id = table[id]; if (id === undefined) break; }
      return out;
    };
    const readChain = (start, len) => {
      const ids = chain(start, fat);
      const out = new Uint8Array(ids.length * size);
      ids.forEach((id, i) => out.set(b.subarray(sec(id), sec(id) + size), i * size));
      return len == null ? out : out.subarray(0, len);
    };
    const dir = readChain(u32(b, 0x30));
    let rootEntry = null, wb = null;
    for (let o = 0; o + 128 <= dir.length; o += 128) {
      const nl = u16(dir, o + 64);
      const name = String.fromCharCode(...Array.from({ length: Math.max(0, nl / 2 - 1) }, (_, i) => u16(dir, o + i * 2)));
      const type = dir[o + 66];
      const ent = { name, type, start: u32(dir, o + 116), size: u32(dir, o + 120) };
      if (type === 5) rootEntry = ent;
      if (type === 2 && /^(workbook|book)$/i.test(name) && !wb) wb = ent;
    }
    if (!wb) throw new Error('In der Datei wurde kein Excel-Tabellenblatt gefunden.');
    if (wb.size >= u32(b, 0x38) || !rootEntry) return readChain(wb.start, wb.size);
    // kleiner Datenstrom im Mini-Stream
    const mini = readChain(rootEntry.start);
    const mfat = [];
    const mf = readChain(u32(b, 0x3c));
    for (let i = 0; i + 4 <= mf.length; i += 4) mfat.push(u32(mf, i));
    const ids = chain(wb.start, mfat);
    const out = new Uint8Array(ids.length * miniSize);
    ids.forEach((id, i) => out.set(mini.subarray(id * miniSize, (id + 1) * miniSize), i * miniSize));
    return out.subarray(0, wb.size);
  }

  /* BIFF-Datensätze in Tabellenraster umsetzen */
  function biffSheets(b) {
    const sheets = [];
    let grid = null, biff8 = false, cp = 'windows-1252', sst = [], pendingFormula = null;
    const names = [];
    const dec = (bytes) => { try { return new TextDecoder(cp === 'utf-16le' ? 'windows-1252' : cp).decode(bytes); } catch { return new TextDecoder('windows-1252').decode(bytes); } };
    const latin1 = (bytes) => { let s = ''; for (let k = 0; k < bytes.length; k++) s += String.fromCharCode(bytes[k]); return s; }; // BIFF8: komprimierte Unicode-Zeichen
    const put = (r, c, v) => {
      if (!grid) { grid = []; sheets.push({ name: names[sheets.length] || `Tabelle${sheets.length + 1}`, grid }); }
      if (v === '' || v == null) return;
      (grid[r] = grid[r] || [])[c] = v;
    };
    /* BIFF8-Zeichenkette (mit Flags) ab Offset lesen */
    const str8 = (d, o, cch) => {
      const fl = d[o]; o++;
      if (fl & 8) o += 2; if (fl & 4) o += 4;
      if (fl & 1) { let s = ''; for (let i = 0; i < cch; i++) s += String.fromCharCode(u16(d, o + i * 2)); return s; }
      return latin1(d.subarray(o, o + cch));
    };
    let o = 0;
    const recs = [];
    while (o + 4 <= b.length) {
      const t = u16(b, o), l = u16(b, o + 2);
      recs.push([t, b.subarray(o + 4, o + 4 + l)]);
      o += 4 + l;
    }
    for (let i = 0; i < recs.length; i++) {
      const [t, d] = recs[i];
      switch (t) {
        case 0x0009: case 0x0209: case 0x0409: case 0x0809: { // BOF
          const ver = u16(d, 0), dt = d.length >= 4 ? u16(d, 2) : 0x10;
          if (t === 0x0809 && ver === 0x0600) biff8 = true;
          if (dt === 0x0005 && t === 0x0809 && ver) grid = 'globals';
          else grid = null;
          break;
        }
        case 0x000a: if (grid === 'globals') grid = null; else grid = null; break; // EOF
        case 0x0042: { const n = u16(d, 0); cp = n === 1200 ? 'utf-16le' : n === 10000 ? 'macintosh' : n >= 1250 && n <= 1258 ? 'windows-' + n : n === 850 ? 'ibm850' : n === 437 ? 'ibm437' : 'windows-1252'; break; }
        case 0x0085: { // BOUNDSHEET
          if (biff8) { const cch = d[6]; names.push(str8(d, 7, cch)); } else { const cch = d[6]; names.push(dec(d.subarray(7, 7 + cch))); }
          break;
        }
        case 0x00fc: { // SST (+ CONTINUE)
          const segs = [d];
          while (i + 1 < recs.length && recs[i + 1][0] === 0x003c) segs.push(recs[++i][1]);
          let si = 0, p = 8;
          const total = u32(d, 4);
          const need = () => { if (p >= segs[si].length) { si++; p = 0; } return si < segs.length; };
          for (let k = 0; k < total && need(); k++) {
            let seg = segs[si];
            if (p + 3 > seg.length) break;
            const cch = u16(seg, p); let fl = seg[p + 2]; p += 3;
            let runs = 0, ext = 0;
            if (fl & 8) { runs = u16(seg, p); p += 2; }
            if (fl & 4) { ext = u32(seg, p); p += 4; }
            let s = '', left = cch;
            while (left > 0) {
              if (p >= segs[si].length) { si++; if (si >= segs.length) break; p = 0; fl = segs[si][0]; p = 1; }
              seg = segs[si];
              const wide = fl & 1, avail = Math.floor((seg.length - p) / (wide ? 2 : 1));
              const n = Math.min(left, avail);
              if (wide) for (let j = 0; j < n; j++) s += String.fromCharCode(u16(seg, p + j * 2));
              else s += latin1(seg.subarray(p, p + n));
              p += n * (wide ? 2 : 1); left -= n;
            }
            let skip = runs * 4 + ext;
            while (skip > 0 && si < segs.length) { const av = segs[si].length - p; if (skip <= av) { p += skip; skip = 0; } else { skip -= av; si++; p = 0; } }
            sst.push(s);
          }
          break;
        }
        default: {
          if (grid === 'globals') break;
          const r = u16(d, 0), c = u16(d, 2);
          if (t === 0x0003) put(r, c, f64(d, 7));                               // NUMBER (BIFF2)
          else if (t === 0x0203) put(r, c, f64(d, 6));                          // NUMBER
          else if (t === 0x0002) put(r, c, u16(d, 7));                          // INTEGER (BIFF2)
          else if (t === 0x027e || t === 0x007e) put(r, c, rk(u32(d, 6)));      // RK
          else if (t === 0x00bd) {                                              // MULRK
            const last = u16(d, d.length - 2);
            for (let k = 0; c + k <= last; k++) put(r, c + k, rk(u32(d, 4 + k * 6 + 2)));
          } else if (t === 0x0004) put(r, c, dec(d.subarray(8, 8 + d[7])).trim());       // LABEL (BIFF2)
          else if (t === 0x0204 || t === 0x00d6) {                                         // LABEL / RSTRING
            const cch = u16(d, 6);
            put(r, c, (biff8 ? str8(d, 8, cch) : dec(d.subarray(8, 8 + cch))).trim());
          } else if (t === 0x00fd) put(r, c, String(sst[u32(d, 6)] ?? '').trim()); // LABELSST
          else if (t === 0x0006 || t === 0x0206 || t === 0x0406) {                // FORMULA (Ergebnis)
            if (d[12] === 0xff && d[13] === 0xff) { if (d[6] === 0) pendingFormula = [r, c]; }
            else put(r, c, f64(d, 6));
          } else if (t === 0x0207 && pendingFormula) {                           // STRING (Formelergebnis)
            const cch = u16(d, 0);
            put(pendingFormula[0], pendingFormula[1], (biff8 ? str8(d, 2, cch) : dec(d.subarray(2, 2 + cch))).trim());
            pendingFormula = null;
          }
        }
      }
    }
    for (const s of sheets) for (let r = 0; r < s.grid.length; r++) s.grid[r] = s.grid[r] || [];
    if (!sheets.length) throw new Error('In der Datei wurden keine Tabellendaten gefunden.');
    return sheets;
  }

  async function readStockWorkbook(buffer) {
    const b = new Uint8Array(buffer);
    if (b.length < 8) throw new Error('Die Datei ist leer.');
    if (b[0] === 0x50 && b[1] === 0x4b) return root.OfferCore.xlsxReadWorkbook(buffer);
    if (u32(b, 0) === 0xe011cfd0 && u32(b, 4) === 0xe11ab1a1) return biffSheets(cfbStream(b));
    const t = u16(b, 0);
    if ([0x0009, 0x0209, 0x0409, 0x0809].includes(t)) return biffSheets(b);
    throw new Error('Die Datei ist keine Excel-Datei (.xls oder .xlsx).');
  }

  /* ======================= Bestandsliste auswerten ======================= */
  const lbl = (v) => String(v ?? '').toLowerCase().replace(/[^a-z0-9äöüß]+/g, '');
  const HEAD = {
    code: ['artnr', 'artikelnr', 'artikelnummer', 'artikel'],
    name: ['bezeichnung', 'artikelbezeichnung', 'artbez'],
    status: ['status'],
    arrival: ['ankunft', 'eingang', 'wareneingang'],
    lot: ['partie', 'charge', 'partienr'],
    mhd: ['mhd', 'mindesthaltbarkeit'],
    kolli: ['kolli', 'karton', 'kartons'],
    kg: ['netto', 'nettokg', 'kgnetto', 'menge', 'kg'],
    ek: ['ekpreis', 'ek'],
  };
  const pad = (n) => String(n).padStart(2, '0');
  function toDate(v, allowSerial) {
    if (v == null || v === '') return null;
    if (typeof v === 'number') {
      if (Number.isInteger(v) && v >= 1010000 && v <= 31129999) {        // TTMMJJJJ als Zahl
        const d = Math.floor(v / 1e6), m = Math.floor(v / 1e4) % 100, y = v % 1e4;
        if (y >= 2000 && y <= 2100 && m >= 1 && m <= 12 && d >= 1 && d <= 31) return `${y}-${pad(m)}-${pad(d)}`;
        return null;
      }
      if (allowSerial && v >= 36526 && v <= 73051) {                     // Excel-Seriendatum
        const dt = new Date(Math.round((v - 25569) * 864e5));
        return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`;
      }
      return null;
    }
    const m = String(v).trim().match(/^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})$/);
    if (!m) return null;
    const y = m[3].length === 2 ? 2000 + +m[3] : +m[3];
    if (+m[2] < 1 || +m[2] > 12 || +m[1] < 1 || +m[1] > 31) return null;
    return `${y}-${pad(m[2])}-${pad(m[1])}`;
  }
  function toNum(v) {
    if (typeof v === 'number') return Number.isFinite(v) ? v : null;
    const s = String(v ?? '').trim().replace(/\s/g, '');
    if (!s) return null;
    const n = Number(/,\d{1,3}$/.test(s) ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, ''));
    return Number.isFinite(n) ? n : null;
  }
  const isCode = (v) => (typeof v === 'number' && Number.isInteger(v) && v >= 0) || /^\d{1,12}$/.test(String(v ?? '').trim());

  function parseSheet(grid) {
    // Kopfzeilen: Spaltenposition je Überschrift (erste 15 Zeilen)
    const head = {};
    for (let r = 0; r < Math.min(grid.length, 15); r++) {
      (grid[r] || []).forEach((v, c) => {
        if (typeof v !== 'string') return;
        const l = lbl(v);
        for (const [f, keys] of Object.entries(HEAD)) if (!(f in head) && keys.includes(l)) head[f] = c;
      });
    }
    // Statusspalte: die Spalte mit den meisten „eingelagert“-Einträgen
    const cnt = new Map();
    grid.forEach((row) => (row || []).forEach((v, c) => { if (typeof v === 'string' && v.trim().toLowerCase() === 'eingelagert') cnt.set(c, (cnt.get(c) || 0) + 1); }));
    if (!cnt.size) return null;
    const stCol = [...cnt.entries()].sort((a, b) => b[1] - a[1])[0][0];
    const rows = [];
    grid.forEach((row, r) => { const v = row && row[stCol]; if (typeof v === 'string' && v.trim() && lbl(v) !== 'status') rows.push({ r, row }); });
    // Spaltenprofil über die Datenzeilen
    const maxC = Math.max(...rows.map((x) => x.row.length));
    const prof = [];
    for (let c = 0; c < maxC; c++) {
      let n = 0, num = 0, int = 0, date = 0, str = 0, code = 0;
      for (const { row } of rows) {
        const v = row[c];
        if (v == null || v === '') continue;
        n++;
        if (typeof v === 'number') { num++; if (Number.isInteger(v)) int++; if (toDate(v)) date++; } else { str++; if (toDate(v)) date++; }
        if (isCode(v)) code++;
      }
      prof[c] = { n, num, int, date, str, code };
    }
    const ok = {
      code: (p) => p.n && p.code / p.n >= 0.6,
      name: (p) => p.n && p.str / p.n >= 0.8,
      arrival: (p) => p.n && p.date / p.n >= 0.8,
      mhd: (p) => p.n && p.date / p.n >= 0.8,
      lot: (p) => p.n && p.date / p.n < 0.5,
      kolli: (p) => p.n && p.int / p.n >= 0.9,
      kg: (p) => p.n && p.num / p.n >= 0.9,
      ek: (p) => p.n && p.num / p.n >= 0.9,
    };
    const cols = { status: stCol };
    const cand = [];
    for (const [f, h] of Object.entries(head)) {
      if (f === 'status' || !ok[f]) continue;
      for (let c = Math.max(0, h - 2); c <= h + 2; c++) if (c !== stCol && prof[c] && ok[f](prof[c])) cand.push([Math.abs(c - h), f, c]);
    }
    cand.sort((a, b) => a[0] - b[0]);
    const taken = new Set([stCol]);
    for (const [, f, c] of cand) if (!(f in cols) && !taken.has(c)) { cols[f] = c; taken.add(c); }
    const missing = ['code', 'name', 'kg'].filter((f) => !(f in cols));
    if (missing.length) {
      const L = { code: 'Art.-Nr.', name: 'Bezeichnung', kg: 'netto' };
      throw new Error(`Spalte ${missing.map((m) => '„' + L[m] + '“').join(', ')} wurde in der Bestandsliste nicht gefunden.`);
    }
    return { cols, rows };
  }

  function findDate(sheets, fileName) {
    for (const s of sheets) for (let r = 0; r < Math.min(s.grid.length, 8); r++) for (const v of s.grid[r] || []) {
      const m = typeof v === 'string' && v.match(/Datum:?\s*(\d{1,2}\.\d{1,2}\.\d{2,4})/i);
      if (m) return toDate(m[1]);
    }
    const m = String(fileName || '').match(/(\d{1,2})\.(\d{1,2})\.(\d{2,4})/);
    return m ? toDate(m[0]) : null;
  }

  function parseStockWorkbook(sheets, fileName) {
    let res = null;
    for (const s of sheets) { res = parseSheet(s.grid); if (res) break; }
    if (!res) throw new Error('Keine Bestandszeilen mit Status „eingelagert“ gefunden – ist das die Bestandsliste aus WinAB?');
    const { cols, rows } = res;
    const stats = { rows: rows.length, stored: 0, other: {}, skipped: 0, noMhd: 0 };
    const by = new Map();
    for (const { row } of rows) {
      const st = String(row[cols.status]).trim();
      if (st.toLowerCase() !== 'eingelagert') { stats.other[st] = (stats.other[st] || 0) + 1; continue; }
      const rawCode = row[cols.code];
      const kg = toNum(row[cols.kg]);
      if (!isCode(rawCode) || kg == null) { stats.skipped++; continue; }
      stats.stored++;
      const code = typeof rawCode === 'number' ? String(rawCode) : String(rawCode).trim();
      const key = normCode(code);
      const mhd = cols.mhd != null ? toDate(row[cols.mhd], true) : null;
      if (!mhd) stats.noMhd++;
      let a = by.get(key);
      if (!a) { a = { code, name: String(row[cols.name] ?? '').trim(), lots: [] }; by.set(key, a); }
      if (!a.name && row[cols.name]) a.name = String(row[cols.name]).trim();
      a.lots.push({
        lot: cols.lot != null && row[cols.lot] != null ? String(row[cols.lot]).trim().slice(0, 20) : '',
        arrival: cols.arrival != null ? toDate(row[cols.arrival], true) : null,
        mhd,
        kolli: cols.kolli != null ? toNum(row[cols.kolli]) : null,
        kg: Math.round(kg * 1000) / 1000,
      });
    }
    const articles = [];
    for (const a of by.values()) {
      const kg = Math.round(a.lots.reduce((s, l) => s + l.kg, 0) * 1000) / 1000;
      if (!(kg > 0)) continue;
      const dated = a.lots.filter((l) => l.mhd);
      const mhd = dated.length ? dated.map((l) => l.mhd).sort()[0] : null;
      const mhdKg = mhd ? Math.round(dated.filter((l) => l.mhd === mhd).reduce((s, l) => s + l.kg, 0) * 1000) / 1000 : null;
      a.lots.sort((x, y) => (x.mhd || '9999').localeCompare(y.mhd || '9999') || (x.arrival || '').localeCompare(y.arrival || ''));
      articles.push({ code: a.code, name: a.name || '(ohne Bezeichnung)', kg, mhd, mhdKg, lots: a.lots });
    }
    articles.sort((x, y) => x.code.localeCompare(y.code, 'de', { numeric: true }));
    return { date: findDate(sheets, fileName), source: fileName || '', articles, stats, columns: cols };
  }

  root.StockCore = { WARENGRUPPEN, warengruppe, normCode, readStockWorkbook, parseStockWorkbook, toDate };
})(typeof window !== 'undefined' ? window : globalThis);
