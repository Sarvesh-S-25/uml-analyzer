/* Builds paper.docx from paper.md in IEEE conference layout.
 *
 *   node build-paper-docx.js            (run from paper/)
 *
 * paper.md is the single source of truth: this script only lays it out, so the
 * Word file can never drift from the verified text. Layout follows the IEEE
 * conference template: US Letter; 0.75" top, 1" bottom, 0.625" side margins;
 * a single-column title block; a two-column 10 pt Times New Roman body with
 * 0.25" gutter; tables and wide figures spanning both columns; captions
 * "TABLE I" above tables and "Fig. 1." below figures; 8 pt references.
 */
const fs = require('fs')
const path = require('path')
const {
  Document, Packer, Paragraph, TextRun, ImageRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, LevelFormat,
  TableLayoutType, VerticalAlign,
} = require('docx')

const HERE = __dirname
// Optional: node build-paper-docx.js [source.md] [output.docx]
const SRC = process.argv[2] || 'paper.md'
const OUT = process.argv[3] || 'paper.docx'
const md = fs.readFileSync(path.resolve(HERE, SRC), 'utf8').replace(/\r\n/g, '\n')

const AUTHOR = 'Sarvesh Sakthivel'
const EMAIL = 'sarveshs2025@gmail.com'

const FONT = 'Times New Roman'
const MONO = 'Courier New'
const PT = (n) => n * 2 // half-points
const IN = (n) => Math.round(n * 1440) // DXA
const PAGE_W = IN(8.5)
const MARGIN_SIDE = IN(0.625)
const TEXT_W = PAGE_W - 2 * MARGIN_SIDE // 7.25"
const GUTTER = IN(0.25)
const COL_W = (TEXT_W - GUTTER) / 2 // 3.5"
const PX_PER_IN = 96

// ---------------------------------------------------------------- inline text

/** **bold**, *italic*, `code`, and \$ escapes into TextRuns. */
function runs(text, base = {}) {
  text = text.replace(/\\\$/g, '$').replace(/\\_/g, '_')
  const out = []
  const re = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g
  let last = 0
  let m
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: FONT, ...base }))
    const tok = m[0]
    if (tok.startsWith('**')) out.push(...runs(tok.slice(2, -2), { ...base, bold: true }))
    else if (tok.startsWith('`')) out.push(new TextRun({ text: tok.slice(1, -1), ...base, font: MONO, size: (base.size || PT(10)) - 2 }))
    else out.push(...runs(tok.slice(1, -1), { ...base, italics: !base.italics }))
    last = m.index + tok.length
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: FONT, ...base }))
  // Placeholders the author must fill are highlighted so none is missed.
  return out.flatMap((r) => r)
}

function placeholderAware(text, base) {
  // Split on <...> placeholders and highlight them.
  text = text.replace(/`(<[^<>]{3,}>)`/g, '$1')
  const parts = text.split(/(<[^<>]{3,}>)/g)
  return parts.flatMap((part) =>
    /^<[^<>]{3,}>$/.test(part)
      ? [new TextRun({ text: part, font: FONT, ...base, highlight: 'yellow' })]
      : runs(part, base))
}

const body = (text, opts = {}) => new Paragraph({
  alignment: opts.align ?? AlignmentType.JUSTIFIED,
  spacing: { after: opts.after ?? 0, line: 228 },
  indent: opts.indent === false ? undefined : { firstLine: IN(0.14) },
  keepNext: opts.keepNext,
  children: placeholderAware(text, { size: PT(opts.size ?? 10), ...(opts.run || {}) }),
})

// ------------------------------------------------------------------- images

function pngSize(file) {
  const b = fs.readFileSync(file)
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), data: b }
}

function figure(src, widthIn) {
  const file = path.join(HERE, src.replace(/\.svg$/, '.png'))
  const { w, h, data } = pngSize(file)
  const wPx = Math.round(widthIn * PX_PER_IN)
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 60 },
    keepNext: true,
    children: [new ImageRun({ type: 'png', data, transformation: { width: wPx, height: Math.round(wPx * h / w) } })],
  })
}

// ------------------------------------------------------------------- tables

const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']

function tableCaption(raw) {
  // "**Table III. Drift over ... .**" -> "TABLE III" / "DRIFT OVER ..."
  const m = raw.match(/^\*\*Table ([IVX]+)\.\s*(.*?)\*\*\s*(.*)$/)
  const number = m[1]
  const title = (m[2] + (m[3] ? ' ' + m[3] : '')).trim()
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 0 }, keepNext: true,
      children: [new TextRun({ text: `TABLE ${number}`, font: FONT, size: PT(8), smallCaps: true })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, keepNext: true,
      children: runs(title, { size: PT(8), smallCaps: true }) }),
  ]
}

function splitRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
}

function table(lines, widthDxa) {
  const header = splitRow(lines[0])
  const rows = lines.slice(2).map(splitRow)
  const ncol = header.length
  // Every column is at least as wide as its longest unbreakable word (so no
  // date, number or identifier splits mid-word); the remaining width goes to
  // the columns whose text would otherwise wrap most.
  const CHAR = 78, PAD = 170
  const measure = (s) => s.split(/\s+/).reduce((acc, tok) => {
    const code = /`/.test(tok)
    const n = tok.replace(/[*`]/g, '').length * (code ? 1.3 : 1)
    return { longest: Math.max(acc.longest, n), total: acc.total + n + 1 }
  }, { longest: 0, total: 0 })
  const cols = header.map((h, i) => [h, ...rows.map((r) => r[i] || '')].map(measure))
  const minW = cols.map((c) => Math.max(...c.map((m) => m.longest)) * CHAR + PAD)
  const wantW = cols.map((c, i) => Math.max(minW[i], Math.min(60, Math.max(...c.map((m) => m.total))) * CHAR + PAD))
  let widths
  const minSum = minW.reduce((a, b) => a + b, 0)
  if (minSum >= widthDxa) {
    widths = minW.map((w) => Math.floor(w * widthDxa / minSum))
  } else {
    const extra = wantW.map((w, i) => w - minW[i])
    const extraSum = extra.reduce((a, b) => a + b, 0) || 1
    const spare = widthDxa - minSum
    widths = minW.map((w, i) => Math.floor(w + Math.min(extra[i], spare * extra[i] / extraSum)))
    const left = widthDxa - widths.reduce((a, b) => a + b, 0)
    widths = widths.map((w) => w + Math.floor(left / ncol))
  }
  widths[ncol - 1] += widthDxa - widths.reduce((a, b) => a + b, 0)

  const border = { style: BorderStyle.SINGLE, size: 4, color: '808080' }
  const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' }
  const cell = (text, i, isHeader, isLast) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 30, bottom: 30, left: 60, right: 60 },
    shading: isHeader ? { type: ShadingType.CLEAR, color: 'auto', fill: 'EDEDED' } : undefined,
    borders: {
      top: isHeader ? border : none,
      bottom: isHeader || isLast ? border : none,
      left: none, right: none,
    },
    children: [new Paragraph({
      alignment: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
      spacing: { after: 0, line: 200 },
      children: runs(text, { size: PT(7.5), bold: isHeader || undefined }),
    })],
  })
  return new Table({
    width: { size: widthDxa, type: WidthType.DXA },
    columnWidths: widths,
    layout: TableLayoutType.FIXED,
    alignment: AlignmentType.CENTER,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true, false)) }),
      ...rows.map((r, ri) => new TableRow({
        cantSplit: true,
        children: header.map((_, i) => cell(r[i] || '', i, false, ri === rows.length - 1)),
      })),
    ],
  })
}

// --------------------------------------------------------------- the parse

const lines = md.split('\n')
let i = 0

// Title, then skip the drafting note and author line up to the abstract.
const title = lines[i++].replace(/^#\s+/, '')
while (i < lines.length && !/^## Abstract/.test(lines[i])) i++

/** Blocks: {wide:boolean, children:[...]}; wide blocks get a 1-column section. */
const front = []
const blocks = [{ wide: false, children: [] }]
const add = (...items) => blocks[blocks.length - 1].children.push(...items)
const addWide = (...items) => { blocks.push({ wide: true, children: items }); blocks.push({ wide: false, children: [] }) }

let section = null // current H2 title
let firstParaInSection = false
let pendingTableCaption = null
let lastWasTable = false
let listInstance = 0

function readParagraph() {
  const buf = []
  while (i < lines.length && lines[i].trim() !== '' && !/^(#|\||!\[|```|\* |\d+\. |---)/.test(lines[i])) {
    buf.push(lines[i].trim()); i++
  }
  return buf.join(' ')
}

function readListItem(marker) {
  const buf = [lines[i].replace(marker, '').trim()]; i++
  while (i < lines.length && /^\s{2,}\S/.test(lines[i])) { buf.push(lines[i].trim()); i++ }
  return buf.join(' ')
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    alignment: AlignmentType.CENTER,
    spacing: { before: 200, after: 100 },
    keepNext: true,
    children: [new TextRun({ text, font: FONT, size: PT(10), smallCaps: true })],
  })
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 120, after: 60 },
    keepNext: true,
    children: [new TextRun({ text, font: FONT, size: PT(10), italics: true })],
  })
}

while (i < lines.length) {
  const line = lines[i]
  const t = line.trim()

  if (t === '' || t === '---') { i++; continue }

  if (/^## /.test(t)) {
    section = t.replace(/^## /, '')
    i++
    if (section === 'Abstract') {
      i++ // blank
      const text = readParagraph()
      front.push(new Paragraph({
        alignment: AlignmentType.JUSTIFIED,
        spacing: { after: 80, line: 220 },
        children: [new TextRun({ text: 'Abstract', font: FONT, size: PT(9), bold: true, italics: true }),
          new TextRun({ text: '—', font: FONT, size: PT(9), bold: true }),
          ...runs(text, { size: PT(9), bold: true })],
      }))
      // Further abstract paragraphs until Index Terms.
      while (i < lines.length && !/^\*\*Index Terms/.test(lines[i])) {
        if (lines[i].trim() === '') { i++; continue }
        front.push(new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 80, line: 220 },
          indent: { firstLine: IN(0.14) }, children: runs(readParagraph(), { size: PT(9), bold: true }) }))
      }
      const terms = readParagraph().replace(/^\*\*Index Terms —\*\*\s*/, '')
      front.push(new Paragraph({
        alignment: AlignmentType.JUSTIFIED,
        spacing: { after: 160, line: 220 },
        children: [new TextRun({ text: 'Index Terms', font: FONT, size: PT(9), bold: true, italics: true }),
          new TextRun({ text: '—', font: FONT, size: PT(9), bold: true }),
          ...runs(terms, { size: PT(9), bold: true })],
      }))
      continue
    }
    add(h1(section.replace(/^([IVX]+)\.\s*/, '$1. ')))
    firstParaInSection = true
    continue
  }

  if (/^### /.test(t)) { add(h2(t.replace(/^### /, ''))); firstParaInSection = true; i++; continue }

  if (/^\*\*Table [IVX]+\./.test(t)) { pendingTableCaption = readParagraph(); continue }

  if (/^\|/.test(t)) {
    const tl = []
    while (i < lines.length && /^\|/.test(lines[i].trim())) { tl.push(lines[i]); i++ }
    const caption = pendingTableCaption ? tableCaption(pendingTableCaption) : []
    pendingTableCaption = null
    if (section === 'IV. Study Design' && /Research questions/i.test(caption.join(''))) { /* none */ }
    // RQ table in the introduction is a list in this paper; every table here spans the page.
    addWide(...caption, table(tl, TEXT_W), new Paragraph({ spacing: { after: 60 }, children: [] }))
    lastWasTable = true
    continue
  }

  if (/^!\[/.test(t)) {
    const src = t.match(/\(([^)]+)\)/)[1]
    i++
    while (i < lines.length && lines[i].trim() === '') i++
    const cap = readParagraph().replace(/^\*(.*)\*$/, '$1')
    const capPara = new Paragraph({
      alignment: AlignmentType.JUSTIFIED,
      spacing: { after: 160, line: 200 },
      children: runs(cap, { size: PT(8) }),
    })
    if (/fig-drift/.test(src)) addWide(figure(src, 6.9), capPara)
    else add(figure(src, 3.35), capPara)
    continue
  }

  if (/^```/.test(t)) {
    i++
    const code = []
    while (i < lines.length && !/^```/.test(lines[i])) { code.push(lines[i]); i++ }
    i++
    addWide(...code.map((c, k) => new Paragraph({
      spacing: { before: k === 0 ? 80 : 0, after: k === code.length - 1 ? 120 : 0, line: 200 },
      children: [new TextRun({ text: c.replace(/\s+#.*$/, (m) => m), font: MONO, size: PT(7.5) })],
    })))
    continue
  }

  if (/^\* /.test(t)) {
    while (i < lines.length && /^\* /.test(lines[i].trim())) {
      add(new Paragraph({ numbering: { reference: 'bullets', level: 0 }, alignment: AlignmentType.JUSTIFIED,
        spacing: { after: 30, line: 228 }, children: placeholderAware(readListItem(/^\*\s+/), { size: PT(10) }) }))
      while (i < lines.length && lines[i].trim() === '' && /^\* /.test((lines[i + 1] || '').trim())) i++
    }
    continue
  }

  if (/^\d+\. /.test(t)) {
    const ref = section === 'I. Introduction' ? 'contributions' : 'steps'
    listInstance += 1
    const instance = listInstance
    while (i < lines.length && /^\d+\. /.test(lines[i].trim())) {
      add(new Paragraph({ numbering: { reference: ref, level: 0, instance }, alignment: AlignmentType.JUSTIFIED,
        spacing: { after: 30, line: 228 }, children: placeholderAware(readListItem(/^\d+\.\s+/), { size: PT(10) }) }))
      while (i < lines.length && lines[i].trim() === '' && /^\d+\. /.test((lines[i + 1] || '').trim())) i++
    }
    continue
  }

  // References: "[n] ..." entries.
  if (section === 'References' && /^\[\d+\]/.test(t)) {
    const text = readParagraph()
    const m = text.match(/^\[(\d+)\]\s*(.*)$/)
    add(new Paragraph({
      alignment: AlignmentType.LEFT,
      spacing: { after: 30, line: 200 },
      indent: { left: IN(0.3), hanging: IN(0.3) },
      children: [new TextRun({ text: `[${m[1]}]\t`, font: FONT, size: PT(8) }), ...runs(m[2], { size: PT(8) })],
      tabStops: [{ type: 'left', position: IN(0.3) }],
    }))
    continue
  }

  // Ordinary paragraph (possibly a table note in italics right after a table).
  const text = readParagraph()
  if (!text) { i++; continue }
  if (section === 'References') continue // the verification note is for the authors, not the paper
  if (lastWasTable && /^\*[^*].*\*$/.test(text)) {
    // Attach the note to the wide block that holds the table.
    blocks[blocks.length - 2].children.push(new Paragraph({
      alignment: AlignmentType.LEFT, spacing: { after: 120, line: 200 },
      children: runs(text.slice(1, -1), { size: PT(7.5), italics: true }),
    }))
    lastWasTable = false
    continue
  }
  lastWasTable = false
  add(body(text, { indent: firstParaInSection ? false : undefined }))
  firstParaInSection = false
}

// ----------------------------------------------------------------- assemble

const PAGE = {
  size: { width: PAGE_W, height: IN(11) },
  margin: { top: IN(0.75), bottom: IN(1), left: MARGIN_SIDE, right: MARGIN_SIDE },
}

const titleBlock = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
    children: [new TextRun({ text: title, font: FONT, size: PT(22) })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 },
    children: [new TextRun({ text: AUTHOR, font: FONT, size: PT(11) })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
    children: [new TextRun({ text: EMAIL, font: FONT, size: PT(10), italics: true })] }),
]

const sections = [
  { properties: { page: PAGE }, children: [...titleBlock, ...front] },
  ...blocks.filter((b) => b.children.length).map((b) => ({
    properties: b.wide
      ? { type: 'continuous', page: PAGE }
      : { type: 'continuous', page: PAGE, column: { count: 2, space: GUTTER, equalWidth: true } },
    children: b.children,
  })),
  // An empty continuous section after the last two-column block makes Word
  // balance the columns on the final page, as IEEE layout expects.
  { properties: { type: 'continuous', page: PAGE }, children: [new Paragraph({ children: [] })] },
]

const doc = new Document({
  creator: AUTHOR,
  title,
  description: 'Conference paper on conformance drift and structure-gated checking',
  styles: {
    default: { document: { run: { font: FONT, size: PT(10) } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: PT(10), smallCaps: true, color: '000000' },
        paragraph: { spacing: { before: 200, after: 100 }, alignment: AlignmentType.CENTER, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: PT(10), italics: true, color: '000000' },
        paragraph: { spacing: { before: 120, after: 60 }, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: IN(0.22), hanging: IN(0.14) } } } }] },
      { reference: 'contributions', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1)', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: IN(0.25), hanging: IN(0.2) } } } }] },
      { reference: 'steps', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1)', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: IN(0.25), hanging: IN(0.2) } } } }] },
    ],
  },
  sections,
})

Packer.toBuffer(doc).then((buf) => {
  const out = path.resolve(HERE, OUT)
  fs.writeFileSync(out, buf)
  console.log(`wrote ${out} (${buf.length} bytes, ${sections.length} sections)`)
})
