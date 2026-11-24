// Client-side checks before upload. The type check uses the file name extension; browsers report
// inconsistent MIME types for .docx and .txt, so the MIME type is not read.

export const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt'] as const
export const MAX_FILE_BYTES = 5 * 1024 * 1024

/** Value for <input accept>. */
export const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',')

export function validateCvFile(file: { name: string; size: number }): string | null {
  const name = file.name.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return `${file.name} is not a PDF, DOCX or TXT file.`
  }
  if (file.size > MAX_FILE_BYTES) {
    return `${file.name} is ${(file.size / (1024 * 1024)).toFixed(1)} MB; the limit is 5 MB.`
  }
  if (file.size === 0) {
    return `${file.name} is empty.`
  }
  return null
}

/** Picks the file to upload from a drop or an input. Returns the file or the inline message. */
export function pickCvFile(files: ArrayLike<File> | null): { file: File } | { rejection: string } {
  if (!files || files.length === 0) return { rejection: 'No file selected.' }
  if (files.length > 1) return { rejection: 'Drop one file at a time.' }
  const file = files[0] as File
  const rejection = validateCvFile(file)
  return rejection === null ? { file } : { rejection }
}
