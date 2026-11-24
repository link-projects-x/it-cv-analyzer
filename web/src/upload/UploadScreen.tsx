import { useId, useRef, useState, type DragEvent } from 'react'
import { readAccessCode, saveAccessCode } from '../api/accessCode'
import { MISSING_CODE_MESSAGE } from '../api/http'
import { ACCEPT_ATTR, pickCvFile } from './validate'

export const PRIVACY_NOTE = 'Your CV is used only to build your profile and is deleted after parsing.'
export const LOCAL_PRIVACY_NOTE = 'Your CV is read in this browser and never leaves it.'

export function UploadScreen({
  rejection,
  demo,
  needsAccessCode = false,
  local = false,
  onFile,
  onReject,
}: {
  rejection: string | null
  /** True when the mock API is in use. */
  demo: boolean
  /** True for the HTTP API, which refuses requests without an access code. */
  needsAccessCode?: boolean
  /** True in static mode: the CV is read in the browser. */
  local?: boolean
  onFile: (file: File) => void
  onReject: (message: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [code, setCode] = useState(readAccessCode)
  const [codeError, setCodeError] = useState<string | null>(null)
  const inputId = useId()
  const errorId = useId()
  const codeId = useId()
  const codeErrorId = useId()
  const needsCode = needsAccessCode

  function handle(files: FileList | null) {
    if (needsCode && !code.trim()) {
      setCodeError(MISSING_CODE_MESSAGE)
      return
    }
    const picked = pickCvFile(files)
    if ('file' in picked) onFile(picked.file)
    else onReject(picked.rejection)
  }

  function onDragOver(e: DragEvent) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
    setDragging(true)
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    handle(e.dataTransfer.files)
  }

  return (
    <section className="up-card" aria-labelledby="upload-h">
      <h2 id="upload-h" className="up-h2">
        Upload your CV
      </h2>
      {needsCode && (
        <div className="up-code">
          <label htmlFor={codeId} className="up-code-label">
            Access code
          </label>
          <input
            id={codeId}
            className="up-code-input"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={code}
            aria-invalid={codeError ? true : undefined}
            aria-describedby={codeError ? codeErrorId : undefined}
            onChange={(e) => {
              const value = e.currentTarget.value
              setCode(value)
              saveAccessCode(value.trim())
              setCodeError(null)
            }}
          />
          {codeError && (
            <p id={codeErrorId} className="up-code-error" role="alert">
              {codeError}
            </p>
          )}
        </div>
      )}
      <div
        className={`up-drop${dragging ? ' up-drop--over' : ''}${rejection ? ' up-drop--rejected' : ''}`}
        data-testid="drop-zone"
        onDragEnter={onDragOver}
        onDragOver={onDragOver}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <p className="up-drop-title">Drop a file here</p>
        <p className="up-drop-hint">PDF, DOCX or TXT, up to 5 MB</p>
        <button
          type="button"
          className="up-btn up-btn--accent"
          onClick={() => inputRef.current?.click()}
          aria-describedby={rejection ? errorId : undefined}
        >
          Choose file
        </button>
        <input
          ref={inputRef}
          id={inputId}
          className="up-visually-hidden"
          type="file"
          accept={ACCEPT_ATTR}
          aria-label="CV file"
          tabIndex={-1}
          onChange={(e) => {
            handle(e.currentTarget.files)
            // Clear so that choosing the same file again fires change.
            e.currentTarget.value = ''
          }}
        />
      </div>
      {rejection && (
        <p id={errorId} className="up-rejection" role="alert">
          {rejection}
        </p>
      )}
      <p className="up-privacy">{local ? LOCAL_PRIVACY_NOTE : PRIVACY_NOTE}</p>
      {demo && (
        <p className="up-demo">
          Demo mode: there is no backend yet. The file is not read or sent; the result is the example response.
        </p>
      )}
    </section>
  )
}
