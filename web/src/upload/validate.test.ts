import { describe, expect, it } from 'vitest'
import { ACCEPT_ATTR, MAX_FILE_BYTES, pickCvFile, validateCvFile } from './validate'

describe('validateCvFile', () => {
  it.each(['cv.pdf', 'cv.docx', 'cv.txt', 'CV.PDF', 'my.cv.Docx'])('accepts %s', (name) => {
    expect(validateCvFile({ name, size: 1000 })).toBeNull()
  })

  it.each(['cv.doc', 'cv.png', 'cv.pdf.exe', 'cv', 'pdf'])('rejects %s by type', (name) => {
    expect(validateCvFile({ name, size: 1000 })).toBe(`${name} is not a PDF, DOCX or TXT file.`)
  })

  it('accepts exactly 5 MB and rejects one byte more', () => {
    expect(MAX_FILE_BYTES).toBe(5 * 1024 * 1024)
    expect(validateCvFile({ name: 'cv.pdf', size: MAX_FILE_BYTES })).toBeNull()
    expect(validateCvFile({ name: 'cv.pdf', size: MAX_FILE_BYTES + 1 })).toBe('cv.pdf is 5.0 MB; the limit is 5 MB.')
    expect(validateCvFile({ name: 'cv.pdf', size: 7.3 * 1024 * 1024 })).toBe('cv.pdf is 7.3 MB; the limit is 5 MB.')
  })

  it('rejects an empty file', () => {
    expect(validateCvFile({ name: 'cv.txt', size: 0 })).toBe('cv.txt is empty.')
  })

  it('accept attribute lists the three extensions', () => {
    expect(ACCEPT_ATTR).toBe('.pdf,.docx,.txt')
  })
})

describe('pickCvFile', () => {
  const file = (name: string, bytes = 10) => new File([new Uint8Array(bytes)], name)

  it('returns the single valid file', () => {
    const f = file('cv.pdf')
    expect(pickCvFile([f])).toEqual({ file: f })
  })

  it('rejects no files and several files', () => {
    expect(pickCvFile(null)).toEqual({ rejection: 'No file selected.' })
    expect(pickCvFile([])).toEqual({ rejection: 'No file selected.' })
    expect(pickCvFile([file('a.pdf'), file('b.pdf')])).toEqual({ rejection: 'Drop one file at a time.' })
  })

  it('passes the validation message through', () => {
    expect(pickCvFile([file('photo.png')])).toEqual({ rejection: 'photo.png is not a PDF, DOCX or TXT file.' })
  })
})
