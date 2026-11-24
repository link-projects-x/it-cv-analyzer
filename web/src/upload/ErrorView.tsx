export function ErrorView({
  fileName,
  message,
  onRetry,
  onOtherFile,
}: {
  fileName: string
  message: string
  onRetry: () => void
  onOtherFile: () => void
}) {
  return (
    <section className="up-card" aria-labelledby="error-h">
      <h2 id="error-h" className="up-h2">
        The CV could not be analyzed
      </h2>
      <p className="up-file">{fileName}</p>
      <p className="up-error" role="alert">
        {message}
      </p>
      <div className="up-actions">
        <button type="button" className="up-btn up-btn--accent" onClick={onRetry}>
          Retry
        </button>
        <button type="button" className="up-btn up-btn--secondary" onClick={onOtherFile}>
          Choose another file
        </button>
      </div>
    </section>
  )
}
