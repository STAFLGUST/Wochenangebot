/* ==========================================================================
   Wochenangebot – gemeinsamer Kern für Frontend und Eingabebereich
   - Excel-Leser (ohne externe Bibliothek)
   - Parser der Angebotsliste → editierbares Datenmodell
   - Anreicherung (Merkmale, Teilstück, Merklisten-Schlüssel …)
   - Vergleich zweier Stände, Validierung
   ========================================================================== */
(function (root) {
  'use strict';

  /* ======================= Konstanten ======================= */

  const CATEGORY_ORDER = ['Rind', 'Kalb', 'Schwein', 'Lamm & Schaf', 'Geflügel', 'Knochen', 'Sonstiges'];
  const CONDITIONS = ['frisch', 'gefroren', 'frisch-gefroren', 'dry-aged', 'unbekannt'];
  const CONDITION_LABELS = {
    'frisch': 'Frisch',
    'gefroren': 'Gefroren / TK',
    'frisch-gefroren': 'Frisch / gefroren',
    'dry-aged': 'Dry Aged',
    'unbekannt': 'Nicht angegeben',
  };
  const PRICE_STATUS_LABELS = { value: 'Mit Preis', request: 'Auf Anfrage', none: 'Ohne Preisangabe' };

  /* ======================= Excel lesen ======================= */

  async function xlsxReadWorkbook(arrayBuffer) {
    const files = await unzip(arrayBuffer, (name) =>
      /^xl\/(workbook\.xml|_rels\/workbook\.xml\.rels|sharedStrings\.xml|worksheets\/[^/]+\.xml)$/i.test(name));
    const wbXml = files['xl/workbook.xml'];
    if (!wbXml) throw new Error('Die Datei enthält keine Excel-Arbeitsmappe (xl/workbook.xml fehlt).');

    const rels = {};
    for (const m of (files['xl/_rels/workbook.xml.rels'] || '').matchAll(/<Relationship\b([^>]*)\/?>/g)) {
      const id = attr(m[1], 'Id');
      let target = attr(m[1], 'Target') || '';
      target = target.startsWith('/') ? target.slice(1) : 'xl/' + target.replace(/^\.\//, '');
      if (id) rels[id] = target;
    }
    const shared = parseSharedStrings(files['xl/sharedStrings.xml'] || '');
    const sheets = [];
    for (const m of wbXml.matchAll(/<sheet\b([^>]*?)\/?>/g)) {
      const a = m[1];
      if (/\bstate="(hidden|veryHidden)"/.test(a)) continue;
      const rid = (a.match(/(?:^|\s)[A-Za-z0-9_]+:id="([^"]*)"/) || [])[1];
      const xml = rels[rid] && files[rels[rid]];
      if (xml) sheets.push({ name: decodeXml(attr(a, 'name') || 'Tabelle'), grid: parseSheet(xml, shared) });
    }
    if (!sheets.length) throw new Error('In der Datei wurde kein lesbares Tabellenblatt gefunden.');
    return sheets;
  }

  function attr(s, name) {
    const m = s.match(new RegExp('(?:^|\\s)' + name + '="([^"]*)"'));
    return m ? m[1] : null;
  }
  function decodeXml(s) {
    return s
      .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
      .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(parseInt(d, 10)))
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&');
  }
  function textOf(frag) {
    let out = '';
    for (const m of frag.replace(/<rPh\b[\s\S]*?<\/rPh>/g, '').matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>|<t\b[^>]*\/>/g)) out += m[1] ? decodeXml(m[1]) : '';
    return out;
  }
  function parseSharedStrings(xml) {
    const list = [];
    for (const m of xml.matchAll(/<si\b[^>]*>([\s\S]*?)<\/si>|<si\b[^>]*\/>/g)) list.push(m[1] ? textOf(m[1]) : '');
    return list;
  }
  function colIndex(letters) { let n = 0; for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64); return n - 1; }
  function parseSheet(xml, shared) {
    const grid = [];
    for (const m of xml.matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
      const a = m[1], body = m[2] || '';
      const rm = (attr(a, 'r') || '').match(/^([A-Z]+)(\d+)$/);
      if (!rm) continue;
      const r = parseInt(rm[2], 10) - 1, c = colIndex(rm[1]), t = attr(a, 't');
      let value;
      if (t === 'inlineStr') value = textOf(body);
      else {
        const v = (body.match(/<v\b[^>]*>([\s\S]*?)<\/v>/) || [])[1];
        if (v == null) continue;
        if (t === 's') value = shared[parseInt(v, 10)] ?? '';
        else if (t === 'str' || t === 'e') value = decodeXml(v);
        else if (t === 'b') value = v === '1' ? 'WAHR' : 'FALSCH';
        else { const num = Number(v); value = Number.isFinite(num) ? num : decodeXml(v); }
      }
      if (value === '' || value == null) continue;
      (grid[r] = grid[r] || [])[c] = value;
    }
    for (let i = 0; i < grid.length; i++) grid[i] = grid[i] || [];
    return grid;
  }
  async function unzip(buffer, filter) {
    const u8 = new Uint8Array(buffer);
    const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    const len = u8.byteLength;
    if (len < 22 || dv.getUint32(0, true) !== 0x04034b50) {
      throw new Error('Die Datei ist keine .xlsx-Datei. Ältere .xls-Dateien bitte in Excel als „Excel-Arbeitsmappe (.xlsx)“ speichern. Kennwortgeschützte Dateien vorher ohne Kennwort speichern.');
    }
    let eocd = -1;
    for (let i = len - 22; i >= Math.max(0, len - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    if (eocd < 0) throw new Error('Die Excel-Datei ist beschädigt (ZIP-Verzeichnis nicht gefunden).');
    const count = dv.getUint16(eocd + 10, true);
    let p = dv.getUint32(eocd + 16, true);
    const dec = new TextDecoder('utf-8');
    const out = {};
    for (let i = 0; i < count; i++) {
      if (dv.getUint32(p, true) !== 0x02014b50) throw new Error('Die Excel-Datei ist beschädigt (ZIP-Eintrag ungültig).');
      const flags = dv.getUint16(p + 8, true), method = dv.getUint16(p + 10, true), compSize = dv.getUint32(p + 20, true);
      const nameLen = dv.getUint16(p + 28, true), extraLen = dv.getUint16(p + 30, true), commentLen = dv.getUint16(p + 32, true);
      const localOff = dv.getUint32(p + 42, true);
      const name = dec.decode(u8.subarray(p + 46, p + 46 + nameLen));
      p += 46 + nameLen + extraLen + commentLen;
      if (!filter(name)) continue;
      if (flags & 1) throw new Error('Die Excel-Datei ist kennwortgeschützt. Bitte ohne Kennwort speichern und erneut importieren.');
      const start = localOff + 30 + dv.getUint16(localOff + 26, true) + dv.getUint16(localOff + 28, true);
      const data = u8.subarray(start, start + compSize);
      let bytes;
      if (method === 0) bytes = data;
      else if (method === 8) bytes = await inflateRaw(data);
      else throw new Error('Nicht unterstütztes Komprimierungsverfahren in der Excel-Datei.');
      out[name] = dec.decode(bytes);
    }
    return out;
  }
  async function inflateRaw(data) {
    if (typeof DecompressionStream === 'undefined') throw new Error('Dieser Browser kann Excel-Dateien nicht entpacken. Bitte einen aktuellen Chrome, Edge, Firefox oder Safari verwenden.');
    const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }

  /* ======================= Hilfen ======================= */

  const isBlank = (v) => v == null || (typeof v === 'string' && v.replace(/\u00a0/g, ' ').trim() === '');
  const str = (v) => (v == null ? '' : String(v));
  const clean = (s) => str(s).replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const low = (s) => clean(s).toLowerCase();
  const isPriceHeader = (v) => typeof v === 'string' && /€\s*\/\s*kg/i.test(v);
  const looksLikeCode = (v) => (typeof v === 'number' && Number.isInteger(v) && v > 0) || (typeof v === 'string' && /^\d{3,}$/.test(clean(v)));
  function colName(c) { let s = ''; c += 1; while (c > 0) { const m = (c - 1) % 26; s = String.fromCharCode(65 + m) + s; c = Math.floor((c - 1) / 26); } return s; }
  const addr = (r, c) => colName(c) + (r + 1);

  /* Preis aus Zelle oder Eingabefeld: Zahl, „23,30“, „a. Anfr.“, „-“, leer */
  function parsePrice(v) {
    if (isBlank(v)) return { status: 'none', raw: '' };
    if (typeof v === 'number') {
      if (!Number.isFinite(v) || v < 0) return { status: 'none', raw: str(v), invalid: true };
      return { status: 'value', value: Number(v.toFixed(4)), raw: str(v) };
    }
    const s = clean(v);
    if (/^[-–—]+$/.test(s)) return { status: 'none', raw: s };
    if (/a\.?\s*anfr|anfrage/i.test(s)) return { status: 'request', raw: s };
    const m = s.replace(/€|\/\s*kg/gi, '').trim().match(/^(\d{1,5}(?:[.,]\d{1,4})?)$/);
    if (m) return { status: 'value', value: Number(Number(m[1].replace(',', '.')).toFixed(4)), raw: s };
    return { status: 'none', raw: s, invalid: true };
  }

  function speciesFromName(t) {
    if (/lamm|weideschaf/.test(t)) return 'Lamm & Schaf';
    if (/kalb/.test(t)) return 'Kalb';
    if (/pute|hähnchen|hühn|\benten|\bente\b|geflügel/.test(t)) return 'Geflügel';
    if (/iberico|spanferkel|schwein|\bsau\b|sau-|^s-/.test(t)) return 'Schwein';
    if (/rind|färse|ochse|bulle/.test(t)) return 'Rind';
    return null;
  }
  function speciesFromHeader(t) {
    if (/knochen/.test(t) && !/am knochen|mit knochen/.test(t)) return 'Knochen';
    if (/geflügel|pute|hähnchen|\benten/.test(t)) return 'Geflügel';
    if (/lamm|schaf/.test(t)) return 'Lamm & Schaf';
    if (/schwein|iberico|spanferkel/.test(t)) return 'Schwein';
    if (/kalb/.test(t)) return 'Kalb';
    if (/rind|färse|ochse|bulle|steer|angus|charoluxe/.test(t)) return 'Rind';
    if (/argentinien|uruguay|paraguay|brasilien|australien|südamerika/.test(t)) return 'Rind';
    return null;
  }
  /* Herkunft als Kürzel (Reihenfolge = Vorrang) */
  const ORIGINS = [
    [/\b4\s*x\s*d\b/, '4xD'], [/\b3\s*x\s*d\b/, '3xD'],
    [/argentinien|\barg\b|\bargent\./, 'ARG'], [/uruguay|\burug\.|\buy\b/, 'UY'], [/paraguay|\bparag\.|\bpy\b/, 'PY'],
    [/brasil/, 'BR'], [/australien/, 'AUS'], [/neus+e+land|\bnzl?\b/, 'NZ'], [/irland|\birl\b/, 'IRL'],
    [/dänemark|\bdän\./, 'DK'], [/schottland/, 'SCO'], [/kanada/, 'CA'], [/\busa\b|us-beef/, 'USA'], [/iberico|spanien/, 'ES'],
    [/\beg\b|\beu\b|europa/, 'EG'], [/deutschland/, 'D'], [/südamerika/, 'Südamerika'],
  ];
  /* frühere ausgeschriebene Herkunftsangaben */
  const ORIGIN_LONG = { 'Argentinien': 'ARG', 'Uruguay': 'UY', 'Paraguay': 'PY', 'Brasilien': 'BR', 'Australien': 'AUS', 'Neuseeland': 'NZ', 'Irland': 'IRL', 'Dänemark': 'DK', 'Deutschland / EU': 'EG', 'Deutschland': 'D', 'Europa': 'EG' };
  const ORIGIN_CODES = ['4xD', '3xD', 'D', 'EG', 'NZ', 'ARG', 'UY', 'PY', 'BR', 'AUS', 'IRL', 'DK', 'SCO', 'CA', 'USA', 'ES', 'Südamerika'];
  function originFrom(t) { for (const [re, label] of ORIGINS) if (re.test(t)) return label; return null; }
  function conditionFrom(t) {
    const f = t.search(/frisch/), g = t.search(/gefr|gefrier|tiefgek|\btk\b/);
    if (f < 0 && g < 0) return null;
    if (f >= 0 && g >= 0) return { f, g };
    return f >= 0 ? 'frisch' : 'gefroren';
  }
  const resolveCond = (c) => (c && typeof c === 'object' ? (c.f < c.g ? 'frisch' : 'gefroren') : c);

  /* Vorschläge für neue/umbenannte Artikel (Eingabebereich) */
  function suggestAttributes(name, groupName, sectionName) {
    const tn = low(name), tg = low(groupName), ts = low(sectionName);
    const nc = conditionFrom(tn);
    let condition = nc && typeof nc === 'object' ? 'frisch-gefroren' : nc;
    if (!condition && /dry\s*aged/.test(tn)) condition = 'dry-aged';
    if (!condition) condition = resolveCond(conditionFrom(tg)) || resolveCond(conditionFrom(ts)) || 'unbekannt';
    const gs = speciesFromHeader(tg);
    return {
      category: gs === 'Knochen' ? 'Knochen' : speciesFromName(tn) || gs || 'Sonstiges',
      origin: originFrom(tn) || originFrom(tg) || null,
      condition,
    };
  }

  /* ======================= Parser ======================= */

  function parseOfferWorkbook(sheets, fileName) {
    let best = null;
    for (const s of sheets) {
      let n = 0;
      for (const row of s.grid) for (const v of row || []) if (isPriceHeader(v)) n++;
      if (!best || n > best.n) best = { s, n };
    }
    if (!best || best.n === 0) throw new Error('In der Datei wurden keine Preisspalten („€ / Kg“) gefunden. Ist das die Wochenangebotsliste?');
    return parseOfferGrid(best.s.grid, { fileName, sheetName: best.s.name });
  }

  function parseOfferGrid(grid, meta) {
    meta = meta || {};
    const issues = [];
    const warn = (cell, message) => issues.push({ level: 'warn', cell, message });
    const info = (cell, message) => issues.push({ level: 'info', cell, message });

    const pcCount = new Map();
    grid.forEach((row) => (row || []).forEach((v, c) => { if (isPriceHeader(v)) pcCount.set(c, (pcCount.get(c) || 0) + 1); }));
    const priceCols = [...pcCount.keys()].filter((c) => c >= 3).sort((a, b) => a - b);
    if (!priceCols.length) throw new Error('Keine Preisspalten („€ / Kg“) gefunden.');
    const blocks = priceCols.map((p, i) => ({ index: i, priceCol: p, codeCol: p - 4, nameCol: p - 3, extraCols: [p - 2, p - 1], group: null, labels: {}, mainLabel: null, last: null }));
    const blockCols = new Set(blocks.flatMap((b) => [b.codeCol, b.nameCol, b.priceCol].concat(b.extraCols)));

    let titleRow = -1, title = '', week = null, year = null;
    for (let r = 0; r < Math.min(grid.length, 12) && titleRow < 0; r++) {
      for (const v of grid[r] || []) {
        if (typeof v === 'string' && /\bKW\s*\d{1,2}\b/i.test(v)) {
          title = clean(v);
          week = parseInt(v.match(/\bKW\s*(\d{1,2})\b/i)[1], 10);
          const y = v.match(/\b(20\d{2})\b/);
          if (y) year = parseInt(y[1], 10);
          titleRow = r;
          break;
        }
      }
    }
    if (meta.fileName) {
      const fm = meta.fileName.match(/KW\s*_?(\d{1,2})\D{0,6}(20\d{2})/i);
      if (fm) {
        if (week == null) week = parseInt(fm[1], 10);
        if (year == null) year = parseInt(fm[2], 10);
        if (titleRow >= 0 && (parseInt(fm[1], 10) !== week || parseInt(fm[2], 10) !== year)) {
          warn(null, `Dateiname (KW ${fm[1]}/${fm[2]}) und Überschrift (KW ${week}/${year}) weichen ab. Übernommen wurde die Angabe aus der Tabelle.`);
        }
      }
    }
    if (week == null) warn(null, 'Kalenderwoche nicht erkannt – bitte im Eingabebereich eintragen.');
    if (year == null) warn(null, 'Jahr nicht erkannt – bitte im Eingabebereich eintragen.');

    const sections = [], groups = [], items = [];
    let section = null;

    const newGroup = (text, r, b) => {
      const name = clean(text).replace(/:\s*$/, '');
      const g = { id: 'g' + (groups.length + 1), name, section: section ? section.name : '', _sec: section ? section.index : -1, _block: b.index, _row: r };
      groups.push(g);
      b.group = g; b.labels = {}; b.mainLabel = null; b.last = null;
    };

    const addItem = (r, b, codeVal, nameVal, priceVal) => {
      const g = b.group;
      const cell = addr(r, b.codeCol);
      if (!g) warn(cell, 'Artikel steht vor der ersten Gruppenüberschrift.');
      const nameRaw = str(nameVal);
      let name = clean(nameRaw);
      if (/\s{2,}[-–]\s*$/.test(nameRaw.replace(/\u00a0/g, ' '))) {
        name = name.replace(/\s*[-–]$/, '');
        info(addr(r, b.nameCol), `Einzelner Bindestrich am Ende von „${name}“ als Füllzeichen gewertet und ausgeblendet.`);
      }
      if (!name) { name = '(ohne Bezeichnung)'; warn(addr(r, b.nameCol), 'Artikel ohne Bezeichnung.'); }

      const price = parsePrice(priceVal);
      if (price.invalid) warn(addr(r, b.priceCol), `Preisangabe „${price.raw}“ nicht lesbar – als „ohne Preisangabe“ übernommen.`);
      delete price.invalid;
      if (b.mainLabel) price.label = b.mainLabel;

      const altPrices = [];
      for (const c of b.extraCols) {
        const v = (grid[r] || [])[c];
        if (isBlank(v)) continue;
        const p = parsePrice(v);
        if (p.invalid) { warn(addr(r, c), `Zusatzwert „${p.raw}“ nicht lesbar – ignoriert.`); continue; }
        p.label = b.labels[c] || 'Weiterer Preis';
        if (!b.labels[c]) warn(addr(r, c), 'Zusätzlicher Preis ohne Spaltenüberschrift übernommen.');
        altPrices.push(p);
      }

      const sug = suggestAttributes(name, g ? g.name : '', g ? g.section : '');
      if (sug.category === 'Sonstiges') warn(cell, `Fleischart für „${name}“ nicht erkannt – unter „Sonstiges“ eingeordnet.`);
      const item = {
        id: 'r' + (r + 1) + colName(b.codeCol),
        code: codeVal == null ? null : String(typeof codeVal === 'number' ? codeVal : clean(codeVal)),
        name,
        category: sug.category,
        origin: sug.origin,
        condition: sug.condition,
        groupId: g ? g.id : null,
        price,
        altPrices,
        cell,
        _sort: [g ? g._sec : -1, b.index, r],
      };
      if (clean(nameRaw) !== name) item.nameRaw = clean(nameRaw);
      items.push(item);
      b.last = item;
      return item;
    };

    for (let r = titleRow + 1; r < grid.length; r++) {
      const row = grid[r] || [];
      const filled = [];
      row.forEach((v, c) => { if (!isBlank(v)) filled.push(c); });
      if (!filled.length) continue;

      if (filled.length === 1 && filled[0] === blocks[0].codeCol && !looksLikeCode(row[filled[0]])) {
        section = { name: clean(row[filled[0]]), index: sections.length };
        sections.push(section.name);
        for (const b of blocks) { b.group = null; b.labels = {}; b.mainLabel = null; b.last = null; }
        continue;
      }
      for (const c of filled) if (!blockCols.has(c)) info(addr(r, c), `Zelle außerhalb der Angebotsspalten („${clean(row[c])}“) nicht übernommen.`);

      for (const b of blocks) {
        const codeV = row[b.codeCol], nameV = row[b.nameCol], priceV = row[b.priceCol];
        if ([codeV, nameV, priceV].concat(b.extraCols.map((c) => row[c])).every(isBlank)) continue;

        if (!isBlank(codeV) && !looksLikeCode(codeV)) {
          newGroup(codeV, r, b);
          if (!isPriceHeader(priceV)) info(addr(r, b.codeCol), `„${clean(codeV)}“ als Gruppenüberschrift gewertet (ohne „€ / Kg“).`);
          continue;
        }
        if (looksLikeCode(codeV)) { addItem(r, b, codeV, nameV, priceV); continue; }

        const nameText = clean(nameV);
        if (nameText) {
          if (isPriceHeader(priceV)) { newGroup(nameV, r, b); continue; }
          if (/^auf anfrage$/i.test(nameText) && b.last && b.last.code == null && b.last.price.status === 'none' && isBlank(priceV)) {
            b.last.price = { status: 'request', raw: 'auf Anfrage' };
            info(addr(r, b.nameCol), `„auf Anfrage“ der Position „${b.last.name}“ aus der Zeile darüber zugeordnet.`);
            continue;
          }
          addItem(r, b, null, nameV, priceV);
          info(addr(r, b.nameCol), `Position „${nameText}“ steht ohne Artikelnummer in der Liste und wurde übernommen.`);
          continue;
        }
        const textCells = b.extraCols.concat([b.priceCol]).filter((c) => {
          const v = row[c];
          return typeof v === 'string' && !isBlank(v) && parsePrice(v).status === 'none' && !/^[-–—\s]+$/.test(v) && !isPriceHeader(v);
        });
        if (textCells.length && b.group && !b.last) {
          for (const c of textCells) { if (c === b.priceCol) b.mainLabel = clean(row[c]); else b.labels[c] = clean(row[c]); }
          continue;
        }
        for (const c of b.extraCols.concat([b.priceCol]).filter((c) => !isBlank(row[c]))) {
          warn(addr(r, c), `Wert „${clean(row[c])}“ ohne Artikel in dieser Zeile – nicht übernommen.`);
        }
      }
    }

    items.sort((a, b) => a._sort[0] - b._sort[0] || a._sort[1] - b._sort[1] || a._sort[2] - b._sort[2]);
    groups.sort((a, b) => a._sec - b._sec || a._block - b._block || a._row - b._row);
    const used = groups.filter((g) => items.some((i) => i.groupId === g.id));
    const orphan = items.filter((i) => !i.groupId);
    if (orphan.length) {
      used.push({ id: 'g0', name: 'Ohne Gruppe', section: '' });
      for (const i of orphan) i.groupId = 'g0';
    }
    for (const i of items) delete i._sort;

    const byCode = new Map();
    for (const it of items) if (it.code) { if (!byCode.has(it.code)) byCode.set(it.code, []); byCode.get(it.code).push(it); }
    for (const [code, list] of byCode) {
      if (list.length > 1) info(list.map((x) => x.cell).join(', '), `Artikelnummer ${code} kommt ${list.length}× vor (${[...new Set(list.map((x) => x.name))].join(' / ')}) – alle Positionen übernommen.`);
    }

    return {
      meta: { title, notice: /freibleibend/i.test(title) ? 'Freibleibendes Angebot' : '', week, year, source: meta.fileName || '', sheetName: meta.sheetName || '' },
      sections: sections.filter((s) => used.some((g) => g.section === s)),
      groups: used.map((g) => ({ id: g.id, name: g.name, section: g.section })),
      items,
      issues,
    };
  }

  /* ======================= Anreicherung ======================= */

  const FEATURES = [
    [/dry\s*aged/, 'Dry Aged'], [/grain\s*fed/, 'Grain Fed'], [/ex\s*chill/, 'ex chilled'], [/prime\s*steer/, 'Prime Steer'],
    [/black\s*angus/, 'Black Angus'], [/4\s*x\s*d\b/, '4xD'], [/\beg\b/, 'EG'], [/\bjb\b|jung\s*bulle/, 'Jungbulle'],
    [/ochse/, 'Ochse'], [/färse/, 'Färse'], [/\bpad\b/, 'PAD'], [/rosé/, 'Rosé'], [/\bhell\b/, 'Hell'],
    [/weideschaf/, 'Weideschaf'], [/iberico/, 'Ibérico'],
  ];
  const CUT_PREFIX = [['entenbrust', 'Entenbrust'], ['entenkeule', 'Entenkeule'], ['putenbrust', 'Putenbrust'], ['hähnchenbrust', 'Hähnchenbrust'],
    ['presa', 'Presa'], ['secreto', 'Secreto'], ['pluma', 'Pluma'], ['gulasch', 'Gulasch'], ['rollbraten', 'Rollbraten'], ['hackfleisch', 'Hackfleisch']];
  const CUTS = [
    ['rippen mit filet', 'Rippen mit Filet'], ['breiter bogen', 'Rippen breiter Bogen'], ['hohe rippe', 'Hohe Rippe'],
    ['falsches filet', 'Falsches Filet'], ['filetköpfe', 'Filetköpfe'], ['hüftfilet', 'Hüftfilet'], ['herz der hüfte', 'Herz der Hüfte'],
    ['filet', 'Filet'], ['roastbeef', 'Roastbeef'], ['entrecote', 'Entrecote'], ['steakhüfte', 'Steakhüfte'],
    ['oberschale', 'Oberschale'], ['unterschale', 'Unterschale'], ['kugel', 'Kugel'], ['tafelspitz', 'Tafelspitz'],
    ['semerrolle', 'Semerrolle'], ['bürgermeisterstück', 'Bürgermeisterstück'], ['flanksteak', 'Flanksteak'],
    ['streifenfleisch', 'Streifenfleisch'], ['hinterbein', 'Hinterbein'], ['rosenstück', 'Rosenstück'],
    ['zungenstück', 'Zungenstück'], ['t-bone', 'T-Bone'], ['tomahawk', 'Tomahawk'], ['cote de bo', 'Côte de Bœuf'],
    ['short ribs', 'Short Ribs'], ['lachs', 'Lachs'], ['krone', 'Krone'], ['keule', 'Keule'], ['sattel', 'Sattel'],
    ['rücken', 'Rücken'], ['hüfte', 'Hüfte'], ['nacken', 'Nacken'], ['brust', 'Brust'], ['leber', 'Leber'],
    ['bäckchen', 'Backe'], ['backe', 'Backe'], ['schaufel', 'Schaufel'], ['kotelett', 'Kotelett'], ['kotlett', 'Kotelett'],
    ['schulter', 'Schulter'], ['abschnitte', 'Abschnitte'], ['haxe', 'Haxe'], ['carree', 'Carree'],
  ];
  function cutFrom(t) {
    const sheep = /weideschaf/.test(t) ? 'Weideschaf-' : '';
    for (const [k, label] of CUT_PREFIX) if (t.includes(k)) return sheep + label;
    for (const [k, label] of CUTS) if (t.includes(k)) return sheep + label;
    const w = t.replace(/^(lamm|iberico|weideschaf|spanferkel|barbarie)\s+/, '').split(/[\s,(]+/)[0] || '';
    return w ? sheep + w.charAt(0).toUpperCase() + w.slice(1) : '';
  }
  function isoWeekRange(week, year) {
    const jan4 = new Date(Date.UTC(year, 0, 4));
    const monday = new Date(jan4);
    monday.setUTCDate(jan4.getUTCDate() - (jan4.getUTCDay() || 7) + 1 + (week - 1) * 7);
    const sunday = new Date(monday);
    sunday.setUTCDate(monday.getUTCDate() + 6);
    return { start: monday.toISOString().slice(0, 10), end: sunday.toISOString().slice(0, 10) };
  }
  const keyPart = (s) => low(s).replace(/[^a-z0-9äöüß]+/g, '');

  /* Liefert eine angereicherte Kopie für die Anzeige; das Modell bleibt unverändert. */
  function enrichOffer(model) {
    const groups = model.groups.map((g) => ({ id: g.id, name: g.name, section: g.section || '' }));
    const gById = new Map(groups.map((g) => [g.id, g]));
    const gIndex = new Map(groups.map((g, i) => [g.id, i]));
    const ordered = model.items
      .map((it, i) => ({ it, i, gi: gIndex.has(it.groupId) ? gIndex.get(it.groupId) : groups.length }))
      .sort((a, b) => a.gi - b.gi || a.i - b.i)
      .map((x) => x.it);
    const keyCount = new Map();
    const items = ordered.map((it, order) => {
      const g = gById.get(it.groupId) || { name: 'Ohne Gruppe', section: '' };
      const tName = low(it.name), tGroup = low(g.name), tSec = low(g.section);
      const features = [];
      for (const [re, label] of FEATURES) if (re.test(tName + ' ' + tGroup) && !features.includes(label)) features.push(label);
      for (const p of [it.price].concat(it.altPrices || [])) if (p.label && /flug|schiff/i.test(p.label) && !features.includes(p.label)) features.push(p.label);
      let key = [it.code || '', keyPart(it.name), keyPart(g.name)].join('|');
      const n = (keyCount.get(key) || 0) + 1;
      keyCount.set(key, n);
      if (n > 1) key += '#' + n;
      return Object.assign({}, it, {
        altPrices: it.altPrices || [],
        group: g.name,
        section: g.section,
        features,
        brand: /fleischmeister/.test(tName) || /fleischmeister/.test(tGroup) || /fleischmeister/.test(tSec) ? 'Fleischmeister' : /charoluxe/.test(tGroup) ? 'Charoluxe' : null,
        cut: cutFrom(tName),
        key,
        order,
      });
    });
    const byCode = new Map();
    for (const it of items) if (it.code) { if (!byCode.has(it.code)) byCode.set(it.code, []); byCode.get(it.code).push(it); }
    for (const list of byCode.values()) if (list.length > 1) for (const it of list) it.sameCode = list.filter((x) => x !== it).map((x) => x.id);
    const meta = Object.assign({}, model.meta);
    if (meta.week && meta.year) { const r = isoWeekRange(meta.week, meta.year); meta.weekStart = r.start; meta.weekEnd = r.end; }
    const sections = [];
    for (const g of groups) if (g.section && !sections.includes(g.section)) sections.push(g.section);
    const counts = new Map();
    for (const it of items) counts.set(it.groupId, (counts.get(it.groupId) || 0) + 1);
    return {
      meta,
      sections,
      groups: groups.filter((g) => counts.get(g.id)).map((g) => Object.assign({}, g, { count: counts.get(g.id) })),
      items,
    };
  }

  /* ======================= Vergleich & Prüfung ======================= */

  const priceSig = (it) => [it.price].concat(it.altPrices || []).map((p) => p.status + (p.value != null ? p.value : '') + (p.label || '')).join('/');
  function matchKey(it, groups) {
    const g = groups.find((x) => x.id === it.groupId);
    return [it.code || '', keyPart(it.name), keyPart(g ? g.name : '')].join('|');
  }
  /* Unterschiede zwischen zwei Modellen (z. B. Entwurf ↔ veröffentlicht) */
  /* Kundenpreis eines Artikels als Vergleichswert (ohne Kennzeichen „aus Vorwoche“) */
  const variantSig = (v) => (!v ? '' : v.status === 'value' ? 'v' + v.value : v.status);
  /* Sonderpreis „solange der Vorrat reicht“: Grundpreis für alle Angebote, je Angebot änderbar */
  function saleFor(it, oid) {
    const s = it && it.sale;
    if (!s || typeof s.value !== 'number') return null;
    const o = s.offers && s.offers[oid];
    if (o) return o.status === 'none' ? null : o.value;
    return s.value;
  }
  const saleSig = (s) => (!s || typeof s.value !== 'number' ? '' : 'v' + s.value + Object.keys(s.offers || {}).sort().map((k) => k + ':' + (s.offers[k].status === 'none' ? 'none' : s.offers[k].value)).join(','));
  function diffOffers(oldM, newM) {
    const res = { added: [], removed: [], priceChanged: [], changed: [], before: {}, variantChanged: [], saleChanged: [] };
    if (!oldM) { res.added = newM.items.map((i) => i.id); return res; }
    const take = (m) => {
      const map = new Map();
      for (const it of m.items) { let k = matchKey(it, m.groups); while (map.has(k)) k += '+'; map.set(k, it); }
      return map;
    };
    const om = take(oldM), nm = take(newM);
    const oldById = new Map(oldM.items.map((i) => [i.id, i]));
    for (const [k, it] of nm) {
      const o = om.get(k) || oldById.get(it.id);
      if (!o) { res.added.push(it.id); continue; }
      if (priceSig(o) !== priceSig(it)) { res.priceChanged.push(it.id); res.before[it.id] = o; }
      else if (o.code !== it.code || o.name !== it.name || o.category !== it.category || o.origin !== it.origin || o.condition !== it.condition) { res.changed.push(it.id); res.before[it.id] = o; }
      const ov = o.variants || {}, nv = it.variants || {};
      for (const k of new Set([...Object.keys(ov), ...Object.keys(nv)])) {
        if (variantSig(ov[k]) !== variantSig(nv[k])) { res.variantChanged.push({ id: it.id, offer: k, from: ov[k] || null, to: nv[k] || null }); res.before[it.id] = res.before[it.id] || o; }
      }
      if (saleSig(o.sale) !== saleSig(it.sale)) { res.saleChanged.push({ id: it.id, from: o.sale || null, to: it.sale || null }); res.before[it.id] = res.before[it.id] || o; }
    }
    const newIds = new Set(newM.items.map((i) => i.id));
    const matched = new Set(Object.values(res.before).map((o) => o.id));
    for (const [k, it] of nm) { const o = om.get(k); if (o) matched.add(o.id); }
    for (const it of newM.items) if (oldById.has(it.id)) matched.add(it.id);
    for (const it of oldM.items) if (!matched.has(it.id)) res.removed.push(it);
    return res;
  }

  /* Prüft ein Modell vor dem Speichern/Veröffentlichen */
  function validateModel(m) {
    const errors = [];
    const warnings = [];
    if (!m.meta || !Number.isInteger(m.meta.week) || m.meta.week < 1 || m.meta.week > 53) errors.push('Kalenderwoche fehlt oder ist ungültig (1–53).');
    if (!m.meta || !Number.isInteger(m.meta.year) || m.meta.year < 2000 || m.meta.year > 2100) errors.push('Jahr fehlt oder ist ungültig.');
    if (!m.items.length) errors.push('Das Angebot enthält keine Artikel.');
    const gids = new Set(m.groups.map((g) => g.id));
    for (const it of m.items) {
      if (!clean(it.name)) errors.push(`Artikel ${it.code || '(ohne Nr.)'} hat keine Bezeichnung.`);
      if (!gids.has(it.groupId)) errors.push(`Artikel „${it.name}“ ist keiner Gruppe zugeordnet.`);
      if (it.code && !/^[0-9A-Za-z.\-/]{1,20}$/.test(it.code)) errors.push(`Artikelnummer „${it.code}“ ist ungültig.`);
      for (const p of [it.price].concat(it.altPrices || [])) {
        if (p.status === 'value' && !(typeof p.value === 'number' && p.value >= 0 && p.value < 100000)) errors.push(`Preis bei „${it.name}“ ist ungültig.`);
      }
    }
    for (const g of m.groups) if (!clean(g.name)) errors.push('Eine Angebotsgruppe hat keinen Namen.');
    const codes = new Map();
    for (const it of m.items) if (it.code) codes.set(it.code, (codes.get(it.code) || 0) + 1);
    const dups = [...codes].filter(([, n]) => n > 1).map(([c]) => c);
    if (dups.length) warnings.push(`Mehrfach vergebene Artikelnummern: ${dups.join(', ')} (zulässig, wenn es verschiedene Varianten sind).`);
    return { errors, warnings };
  }

  /* „frisch“ gehört in den Zustand, nicht in die Bezeichnung.
     „frisch/gefr.“ (frisch-gefroren) bleibt unverändert. */
  function stripFrisch(name) {
    const src = String(name ?? '');
    if (!/frisch/i.test(src)) return src;
    if (/frisch\s*[/-]\s*(gefr|tk|tief)|gefr\w*\.?\s*[/-]\s*frisch/i.test(src)) return src;
    const M = '\u0000';
    let s = src.replace(/(^|[^A-Za-zÄÖÜäöüß])frisch(?![A-Za-zÄÖÜäöüß])\.?/gi, (m, pre) => pre + M);
    s = s.replace(new RegExp(`[\\s,;]*${M}[\\s,.;]*$`), '')
      .replace(new RegExp(`^[\\s,;]*${M}[\\s,;]*`), '')
      .replace(new RegExp(`(,\\s*)${M}\\s*,\\s*`, 'g'), '$1')
      .replace(new RegExp(`\\s*${M}\\s*`, 'g'), ' ')
      .replace(/\s{2,}/g, ' ').trim();
    return s || src;
  }

  /* Bezeichnung und Herkunft vereinheitlichen:
     – „frisch“ nur im Zustand
     – Eigenmarke „Fleischmeister“ (Gruppe/Bereich) steht in der Bezeichnung
     – Herkunft als Kürzel; von Hand gesetzte Kürzel bleiben */
  function normalizeItem(it, group) {
    const g = group || {};
    let changed = false;
    const n0 = it.name;
    let name = stripFrisch(n0);
    if (name !== n0 && it.condition === 'unbekannt') { it.condition = 'frisch'; }
    if (/fleischmeister/i.test(`${g.name || ''} ${g.section || ''}`) && !/fleischmeister/i.test(name)) name = name.replace(/^([^,]+?)(\s*,|$)/, '$1 Fleischmeister$2');
    if (name !== n0) { it.name = name; changed = true; }
    if (!it.origin || ORIGIN_LONG[it.origin] !== undefined) {
      const o = originFrom(low(n0)) || originFrom(low(g.name || '')) || ORIGIN_LONG[it.origin] || it.origin || null;
      if ((o || null) !== (it.origin || null)) { it.origin = o; changed = true; }
    }
    return changed;
  }

  /* ======================= Gemeinsames Bearbeiten =======================
     Drei-Wege-Abgleich: base = Stand, auf dem die eigenen Änderungen beruhen; mine = eigener Stand;
     theirs = inzwischen gespeicherter Stand anderer. Ergebnis enthält beide Änderungen – je Feld,
     je Artikel und je Kundenangebotspreis. Ändern beide dasselbe Feld unterschiedlich, gilt die eigene
     Eingabe (conflicts nennt diese Fälle). Gelöschte Artikel/Gruppen bleiben gelöscht. */
  function canon(v) {
    if (v === undefined) return 'u';
    if (v === null || typeof v !== 'object') return JSON.stringify(v);
    if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
    return '{' + Object.keys(v).filter((k) => v[k] !== undefined).sort().map((k) => JSON.stringify(k) + ':' + canon(v[k])).join(',') + '}';
  }
  const same = (a, b) => canon(a) === canon(b);
  const cloneJ = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
  function merge3(b, m, t, onConflict) {
    if (same(m, b)) return cloneJ(t);
    if (same(t, b) || same(m, t)) return cloneJ(m);
    onConflict(m, t);
    return cloneJ(m);
  }
  function mergeFields(b, m, t, skip, onConflict) {
    const out = {};
    const keys = new Set([...Object.keys(b || {}), ...Object.keys(m || {}), ...Object.keys(t || {})]);
    for (const k of keys) {
      if (skip.includes(k)) continue;
      const v = merge3((b || {})[k], (m || {})[k], (t || {})[k], (mv, tv) => onConflict(k, mv, tv));
      if (v !== undefined) out[k] = v;
    }
    return out;
  }
  function mergeOrder(baseIds, mineIds, theirIds, keep) {
    const common = (arr, other) => arr.filter((id) => other.includes(id));
    const theirsReordered = !same(common(theirIds, baseIds), common(baseIds, theirIds));
    const [prim, sec] = theirsReordered ? [theirIds, mineIds] : [mineIds, theirIds];
    const out = prim.filter((id) => keep.has(id));
    for (let i = 0; i < sec.length; i++) {
      const id = sec[i];
      if (!keep.has(id) || out.includes(id)) continue;
      let at = 0;
      for (let j = i - 1; j >= 0; j--) { const k = out.indexOf(sec[j]); if (k >= 0) { at = k + 1; break; } }
      out.splice(at, 0, id);
    }
    for (const id of keep) if (!out.includes(id)) out.push(id);
    return out;
  }
  function mergeList(bl, ml, tl, label, conflicts, mergeOne) {
    const bm = new Map((bl || []).map((x) => [x.id, x]));
    const mm = new Map((ml || []).map((x) => [x.id, x]));
    const tm = new Map((tl || []).map((x) => [x.id, x]));
    const res = new Map();
    for (const id of new Set([...bm.keys(), ...mm.keys(), ...tm.keys()])) {
      const b = bm.get(id), m = mm.get(id), t = tm.get(id);
      if (!b) { res.set(id, cloneJ(m && t ? mergeOne(undefined, m, t) : m || t)); continue; }
      if (!m || !t) {
        const left = m || t;
        if (left && !same(left, b)) conflicts.push({ kind: label, id, name: left.name || b.name || id, field: 'deleted', by: m ? 'theirs' : 'mine' });
        continue; // gelöscht bleibt gelöscht
      }
      res.set(id, mergeOne(b, m, t));
    }
    const ids = mergeOrder((bl || []).map((x) => x.id), (ml || []).map((x) => x.id), (tl || []).map((x) => x.id), new Set(res.keys()));
    return ids.map((id) => res.get(id));
  }
  function mergeModels(base, mine, theirs) {
    const E = { meta: {}, groups: [], items: [] };
    base = base || E; theirs = theirs || E;
    const conflicts = [];
    const meta = mergeFields(base.meta, mine.meta, theirs.meta, [], (f, mv, tv) => conflicts.push({ kind: 'meta', id: f, name: 'Kopfdaten', field: f, mine: mv, theirs: tv }));
    const groups = mergeList(base.groups, mine.groups, theirs.groups, 'group', conflicts, (b, m, t) => ({ id: m.id, ...mergeFields(b, m, t, ['id'], (f, mv, tv) => conflicts.push({ kind: 'group', id: m.id, name: m.name, field: f, mine: mv, theirs: tv })) }));
    const items = mergeList(base.items, mine.items, theirs.items, 'item', conflicts, (b, m, t) => {
      const c = (f, mv, tv) => conflicts.push({ kind: 'item', id: m.id, name: (m.code ? m.code + ' · ' : '') + m.name, field: f, mine: mv, theirs: tv });
      const it = { id: m.id, ...mergeFields(b, m, t, ['id', 'variants'], c) };
      const v = mergeFields((b || {}).variants, m.variants, t.variants, [], (oid, mv, tv) => c('variant:' + oid, mv, tv));
      if (Object.keys(v).length) it.variants = v;
      return it;
    });
    // Artikel brauchen eine vorhandene Gruppe – eine inzwischen gelöschte Gruppe bleibt dann erhalten
    const gids = new Set(groups.map((g) => g.id));
    for (const it of items) {
      if (gids.has(it.groupId)) continue;
      const g = [mine, theirs, base].map((x) => (x.groups || []).find((y) => y.id === it.groupId)).find(Boolean);
      if (g) { groups.push(cloneJ(g)); gids.add(g.id); }
    }
    const sections = [];
    for (const g of groups) if (g.section && !sections.includes(g.section)) sections.push(g.section);
    const out = { ...cloneJ(mine), meta, sections, groups, items };
    const before = new Map((mine.items || []).map((x) => [x.id, canon(x)]));
    const remoteItems = items.filter((x) => before.get(x.id) !== canon(x)).map((x) => x.id);
    const removed = (mine.items || []).filter((x) => !items.some((y) => y.id === x.id)).map((x) => x.id);
    return { model: out, conflicts, remoteItems, removed, changed: !same(out, mine) };
  }

  const api = {
    CATEGORY_ORDER, CONDITIONS, CONDITION_LABELS, PRICE_STATUS_LABELS,
    xlsxReadWorkbook, parseOfferWorkbook, parseOfferGrid, parsePrice, suggestAttributes,
    enrichOffer, isoWeekRange, diffOffers, validateModel, clean, stripFrisch, normalizeItem, ORIGIN_CODES, mergeModels, sameModel: same, saleFor,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.OfferCore = api;
})(typeof window !== 'undefined' ? window : globalThis);
