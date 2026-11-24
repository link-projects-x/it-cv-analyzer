// CV file -> plain text in the browser. TXT as is, DOCX from word/document.xml inside the zip,
// PDF through pdf.js (loaded only when a PDF arrives).

export class CvReadError extends Error {}

export async function extractText(file: File): Promise<string> {
  const name = file.name.toLowerCase()
  if (name.endsWith('.txt')) return file.text()
  if (name.endsWith('.docx')) return docxText(new Uint8Array(await file.arrayBuffer()))
  if (name.endsWith('.pdf')) return pdfText(await file.arrayBuffer())
  throw new CvReadError('Only PDF, DOCX and TXT files can be read.')
}

// Minimal zip reader: finds one entry through the central directory and inflates it with
// DecompressionStream("deflate-raw"). DOCX files use stored (0) or deflate (8) entries.
async function zipEntry(bytes: Uint8Array, wanted: string): Promise<Uint8Array> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  let eocd = -1
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
    if (view.getUint32(i, true) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new CvReadError('The DOCX file is damaged (no zip directory).')
  const count = view.getUint16(eocd + 10, true)
  let p = view.getUint32(eocd + 16, true)
  const decoder = new TextDecoder()
  for (let n = 0; n < count; n++) {
    if (view.getUint32(p, true) !== 0x02014b50) break
    const method = view.getUint16(p + 10, true)
    const compressed = view.getUint32(p + 20, true)
    const nameLen = view.getUint16(p + 28, true)
    const extraLen = view.getUint16(p + 30, true)
    const commentLen = view.getUint16(p + 32, true)
    const local = view.getUint32(p + 42, true)
    const entryName = decoder.decode(bytes.subarray(p + 46, p + 46 + nameLen))
    if (entryName === wanted) {
      const dataStart = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true)
      const data = bytes.subarray(dataStart, dataStart + compressed)
      if (method === 0) return data
      if (method !== 8) throw new CvReadError('The DOCX file uses an unsupported compression.')
      const stream = new Blob([data.slice()]).stream().pipeThrough(new DecompressionStream('deflate-raw'))
      return new Uint8Array(await new Response(stream).arrayBuffer())
    }
    p += 46 + nameLen + extraLen + commentLen
  }
  throw new CvReadError('The DOCX file has no document text.')
}

export async function docxText(bytes: Uint8Array): Promise<string> {
  const xml = new TextDecoder().decode(await zipEntry(bytes, 'word/document.xml'))
  return xml
    .replace(/<w:tab\/>/g, '\t')
    .replace(/<\/w:p>|<w:br\/>/g, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
}

async function pdfText(buffer: ArrayBuffer): Promise<string> {
  const pdfjs = await import('pdfjs-dist')
  const worker = await import('pdfjs-dist/build/pdf.worker.min.mjs?url')
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default
  let doc
  try {
    doc = await pdfjs.getDocument({ data: buffer }).promise
  } catch {
    throw new CvReadError('Could not open the PDF.')
  }
  const lines: string[] = []
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i)
    const content = await page.getTextContent()
    let line = ''
    for (const item of content.items) {
      if (!('str' in item)) continue
      line += item.str
      if (item.hasEOL) {
        lines.push(line)
        line = ''
      } else {
        line += ' '
      }
    }
    if (line) lines.push(line)
  }
  const text = lines.join('\n')
  if (!text.trim()) throw new CvReadError('The PDF has no text layer (a scan?). Try DOCX or TXT.')
  return text
}
